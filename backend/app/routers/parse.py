"""批次 / 上传 / 解析进度（页 2、页 3、页 12 异常态）。"""

import asyncio
import json
import queue
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func
from sqlmodel import Session, delete, select
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.db import engine, get_session
from app.enums import STAGES, BatchStatus, StageStatus, TagTarget, VideoStatus
from app.engines.base import available_asr, available_ocr, resolve_asr_name
from app.media import display_name, media_url
from app.models import (
    Artifact, ConflictRecord, Evidence, KnowledgeItem, Note, Revision, Segment, TagBinding, Video, VideoBatch
)
from app.pipeline import bus, parse_batch, parse_mutex, retry_video, sanitize_error

router = APIRouter(prefix="/api", tags=["parse"])

_ALLOWED_SUFFIX = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
_MAX_FILE_BYTES = 2 * 1024 ** 3
_MAX_FILES = 20
# 批次总大小上限：20 个 × 2GB 的理论上限没有意义，磁盘会先写满；20GB 已覆盖一个完整课程包
_MAX_BATCH_BYTES = 20 * 1024 ** 3
_MULTIPART_SLACK = 10 * 1024 ** 3 // 100   # multipart 编码与表单字段的开销余量（约 100MB）
_TRANSCRIPT_LIMIT = 5000
_TERMINAL = (BatchStatus.SUCCEEDED, BatchStatus.PARTIAL, BatchStatus.FAILED)
_TERMINAL_VALUES = tuple(s.value for s in _TERMINAL)


def _video_view(video: Video) -> dict:
    """UI 只需要原始文件名和 /media URL；不回显本机绝对落盘路径。"""
    return {
        "id": video.id,
        "file_name": display_name(video.path, video.batch_id),
        "media_url": media_url(video.path),
        "duration_ms": video.duration_ms,
        "status": video.status.value,
        "error": video.error,
        "stages": {s.value: getattr(video, f"{s.value}_status").value for s in STAGES},
    }


def _terminal_event(batch: VideoBatch, seq: int | None = None) -> dict:
    """给「订阅前批次已结束」的重连者补一条终态事件，字段形状与 ProgressBus.emit 一致。"""
    event = {
        "batch_id": batch.id, "video_id": None, "stage": "batch", "status": batch.status.value,
        "message": "", "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if seq is not None:
        event["seq"] = seq
    return event


_TERMINAL_VIDEO_VALUES = tuple(s.value for s in (VideoStatus.SUCCEEDED, VideoStatus.PARTIAL, VideoStatus.FAILED))


def _is_video_terminal(event: dict) -> bool:
    return (event.get("video_id") is not None and event.get("stage") == "batch"
            and event.get("status") in _TERMINAL_VIDEO_VALUES)


def _is_batch_terminal(event: dict) -> bool:
    return (event.get("video_id") is None and event.get("stage") == "batch"
            and event.get("status") in _TERMINAL_VALUES)


def _run_batch(batch_id: int) -> None:
    """后台任务用独立会话——请求会话在响应返回时就关了。"""
    try:
        with Session(engine) as session:
            batch = session.get(VideoBatch, batch_id)
            if not batch:
                return
            try:
                parse_batch(session, batch)
            except Exception as exc:
                # parse_batch 内部已尽量兜底；这里再兜一层，避免后台任务异常被 Starlette 吞掉
                session.rollback()
                batch = session.get(VideoBatch, batch_id)
                if batch is not None:
                    batch.status = BatchStatus.FAILED
                    session.add(batch)
                    session.commit()
                    bus.emit(batch.id, None, "batch", BatchStatus.FAILED.value,
                             f"批次解析异常：{sanitize_error(str(exc))}"[:200])
    finally:
        parse_mutex.release(batch_id)


@router.post("/batches", status_code=201)
async def create_batch(
    background: BackgroundTasks,
    request: Request,
    files: list[UploadFile] = File(...),
    name: str = Form("未命名批次"),
    session: Session = Depends(get_session),
):
    if len(name) > 80:
        raise HTTPException(422, "批次名过长（不超过 80 字）")
    if not files:
        raise HTTPException(422, "未收到有效文件")
    if len(files) > _MAX_FILES:
        raise HTTPException(422, f"单批最多 {_MAX_FILES} 个文件（收到 {len(files)} 个），请分批上传")
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() \
            and int(content_length) > _MAX_BATCH_BYTES + _MULTIPART_SLACK:
        # 在落任何盘之前拒绝：避免 20GB 的请求体先传完再报错
        raise HTTPException(413, "上传总量超过批次大小上限（20GB），请分批上传")
    settings = get_settings()
    root = Path(settings.media_root)
    root.mkdir(parents=True, exist_ok=True)

    batch = VideoBatch(name=name or "未命名批次", video_count=0, status=BatchStatus.PENDING)
    session.add(batch)
    session.commit()
    session.refresh(batch)
    if not parse_mutex.claim(batch.id):
        # 顺序处理口径：同一时间只允许一个批次在解析
        session.delete(batch)
        session.commit()
        raise HTTPException(409, "已有批次正在解析，请等待完成后再试")

    seen: set[str] = set()
    rejected: list[dict] = []
    current_name = ""
    batch_bytes = 0
    try:
        for upload in files:
            filename = Path(upload.filename or "").name
            if not filename:
                rejected.append({"filename": "(空文件名)", "reason": "文件名为空"})
                continue
            if Path(filename).suffix.lower() not in _ALLOWED_SUFFIX:
                rejected.append({"filename": filename, "reason": "不支持的格式，可选 mp4/mov/mkv/avi/webm"})
                continue
            # Windows 文件系统大小写不敏感；同名判断也要按 casefold，否则会写同一目标路径
            name_key = filename.casefold()
            if name_key in seen:
                rejected.append({"filename": filename, "reason": "与批内已有文件同名"})
                continue
            if batch_bytes >= _MAX_BATCH_BYTES:
                rejected.append({"filename": filename, "reason": "超出批次总大小上限（20GB）"})
                continue
            current_name = filename
            dest = root / f"{batch.id}_{filename}"
            written = 0
            too_large = False
            with dest.open("wb") as fh:                     # 分块落盘，大视频不整读进内存
                while chunk := await upload.read(1024 * 1024):
                    written += len(chunk)
                    batch_bytes += len(chunk)
                    if written > _MAX_FILE_BYTES:
                        too_large = True
                        break
                    if batch_bytes > _MAX_BATCH_BYTES:
                        too_large = True
                        break
                    fh.write(chunk)
            if too_large:
                dest.unlink(missing_ok=True)
                batch_bytes -= written
                if written > _MAX_FILE_BYTES:
                    rejected.append({"filename": filename, "reason": "文件超过 2GB 上限"})
                else:
                    rejected.append({"filename": filename, "reason": "超出批次总大小上限（20GB）"})
                continue
            seen.add(name_key)
            session.add(Video(batch_id=batch.id, path=str(dest)))
            batch.video_count += 1
    except Exception as exc:
        # 上传中断/写盘失败：不能留下 PENDING 孤儿批次与半截文件
        parse_mutex.release(batch.id)
        session.rollback()
        for leftover in root.glob(f"{batch.id}_*"):
            leftover.unlink(missing_ok=True)
        batch = session.get(VideoBatch, batch.id)
        if batch is not None:
            session.delete(batch)
            session.commit()
        raise HTTPException(500, f"上传写入失败：{current_name or '未知文件'}") from exc

    if batch.video_count == 0:
        # 一条有效视频都没有：不落空批次，把每个文件被拒的原因直接带回前端
        parse_mutex.release(batch.id)
        session.delete(batch)
        session.commit()
        for leftover in root.glob(f"{batch.id}_*"):
            leftover.unlink(missing_ok=True)
        reason = "；".join(f"{r['filename']}（{r['reason']}）" for r in rejected) or "未收到有效文件"
        raise HTTPException(422, f"没有可解析的视频：{reason}")
    session.add(batch)
    session.commit()
    session.refresh(batch)
    bus.forget(batch.id)   # SQLite 可能复用主键：新批次绝不能回放已删除批次的旧事件

    background.add_task(_run_batch, batch.id)
    return {"id": batch.id, "name": batch.name, "video_count": batch.video_count, "rejected": rejected}


@router.get("/batches")
def list_batches(session: Session = Depends(get_session)):
    batches = session.exec(select(VideoBatch).order_by(VideoBatch.id.desc())).all()
    # 一次 group by 拿全部批次的视频状态分布，库页卡片不用点进详情就能看出「2 成功 1 失败」
    rows = session.exec(
        select(Video.batch_id, Video.status, func.count())
        .group_by(Video.batch_id, Video.status)).all()
    counts: dict[int, dict[str, int]] = {}
    for batch_id, status, cnt in rows:
        counts.setdefault(batch_id, {})[status.value] = cnt
    return [{
        "id": b.id, "name": b.name, "status": b.status.value,
        "video_count": b.video_count, "created_at": b.created_at,
        "video_status_counts": counts.get(b.id, {}),
    } for b in batches]


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, session: Session = Depends(get_session)):
    batch = session.get(VideoBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "批次不存在")
    videos = session.exec(select(Video).where(Video.batch_id == batch_id).order_by(Video.id)).all()
    return {
        "id": batch.id, "name": batch.name, "status": batch.status.value,
        "videos": [_video_view(v) for v in videos],
    }


@router.post("/batches/{batch_id}/parse")
def reparse_batch(batch_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    batch = session.get(VideoBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "批次不存在")
    if batch.status not in _TERMINAL:
        raise HTTPException(409, "批次解析中，结束后才能重跑")
    if not parse_mutex.claim(batch_id):
        raise HTTPException(409, "已有批次正在解析，请等待完成后再试")
    # 同步置 RUNNING 并清掉旧事件：否则前端 POST 后立刻打开 SSE 会先收到旧终态并断流
    bus.reset(batch_id)
    batch.status = BatchStatus.RUNNING
    videos = session.exec(select(Video).where(Video.batch_id == batch_id)).all()
    for video in videos:
        video.status = VideoStatus.PENDING
        video.error = ""
        for stage in STAGES:
            setattr(video, f"{stage.value}_status", StageStatus.PENDING)
        session.add(video)
    session.add(batch)
    session.commit()
    background.add_task(_run_batch, batch_id)
    return {"ok": True}


@router.delete("/batches/{batch_id}", status_code=204)
def delete_batch(batch_id: int, session: Session = Depends(get_session)):
    """删除批次：仅终态可删；级联清派生数据、视频行、标签绑定、上传文件与帧目录。

    只动运行时数据，不改 ER 图口径（docs/产品定义.md §六的表一个不多一个不少）。
    """
    batch = session.get(VideoBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "批次不存在")
    if batch.status not in _TERMINAL and not (
            batch.status == BatchStatus.PENDING and batch.video_count == 0):
        raise HTTPException(409, "批次解析中，结束后才能删除")

    videos = session.exec(select(Video).where(Video.batch_id == batch_id)).all()
    for v in videos:
        item_ids = session.exec(select(KnowledgeItem.id).where(KnowledgeItem.video_id == v.id)).all()
        if item_ids:
            session.exec(delete(Note).where(Note.item_id.in_(item_ids)))
            session.exec(delete(Revision).where(Revision.item_id.in_(item_ids)))
            session.exec(delete(Artifact).where(Artifact.item_id.in_(item_ids)))
            session.exec(delete(ConflictRecord).where(ConflictRecord.item_id.in_(item_ids)))
            session.exec(delete(TagBinding).where(
                (TagBinding.target_type == TagTarget.ITEM) & (TagBinding.target_id.in_(item_ids))))
            session.exec(delete(KnowledgeItem).where(KnowledgeItem.id.in_(item_ids)))
        session.exec(delete(Evidence).where(Evidence.video_id == v.id))
        session.exec(delete(Segment).where(Segment.video_id == v.id))
        session.exec(delete(TagBinding).where(
            (TagBinding.target_type == TagTarget.VIDEO) & (TagBinding.target_id == v.id)))
        shutil.rmtree(Path(get_settings().media_root) / "frames" / str(v.id), ignore_errors=True)
    for v in videos:
        Path(v.path).unlink(missing_ok=True)
    session.exec(delete(Video).where(Video.batch_id == batch_id))
    session.delete(batch)
    session.commit()
    bus.forget(batch_id)
    return None


@router.post("/videos/{video_id}/retry")
def retry(video_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    """单条重试，不重跑整批（用例 3）。"""
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(404, "视频不存在")
    batch = session.get(VideoBatch, video.batch_id)
    if video.status == VideoStatus.RUNNING or (batch and batch.status == BatchStatus.RUNNING):
        raise HTTPException(409, "该视频或批次正在解析中，结束后才能重试")
    if not parse_mutex.claim(video.batch_id):
        raise HTTPException(409, "已有批次正在解析，请等待完成后再试")

    bus.reset(video.batch_id)
    video.status = VideoStatus.RUNNING
    video.error = ""
    for stage in STAGES:
        setattr(video, f"{stage.value}_status", StageStatus.PENDING)
    session.add(video)
    if batch is not None:
        batch.status = BatchStatus.RUNNING
        session.add(batch)
    session.commit()

    def _one(vid: int) -> None:
        try:
            with Session(engine) as s:
                retry_video(s, vid)
        finally:
            parse_mutex.release(video.batch_id)

    background.add_task(_one, video_id)
    return {"ok": True}


@router.get("/batches/{batch_id}/progress", response_class=EventSourceResponse)
async def progress(batch_id: int, video_events: bool = Query(False)):
    """批次进度 SSE。FastAPI 只有显式指定 EventSourceResponse 才走 text/event-stream 分支，
    否则生成器端点按 application/jsonl 输出，浏览器 EventSource 直接收不到。

    video_events=1 时额外下发单条视频终态事件（video_id 非空）；默认关闭以兼容
    仍按「stage=batch 即整批结束」判断的旧前端。新前端订阅时显式开启。
    """
    with Session(engine) as probe:
        batch = probe.get(VideoBatch, batch_id)
    if batch is None:
        # 404 必须在开流前抛：生成器里的异常发生在响应已开始之后，Starlette 无法再改状态码
        raise HTTPException(404, "批次不存在")

    def _keep(event: dict) -> bool:
        return video_events or not _is_video_terminal(event)

    async def _stream():
        q, history = bus.subscribe(batch_id)
        try:
            for event in history:
                if event.get("batch_id") == batch_id and _keep(event):
                    yield {"event": "stage", "data": json.dumps(event, ensure_ascii=False)}
            if history and _is_batch_terminal(history[-1]):
                return
            # 订阅前批次可能已经跑完（进度页刷新后重连），历史为空时补一条终态
            if batch.status in _TERMINAL:
                seq = (history[-1].get("seq", 0) + 1) if history else None
                yield {"event": "stage", "data": json.dumps(_terminal_event(batch, seq), ensure_ascii=False)}
                return
            while True:
                try:
                    event = await asyncio.to_thread(q.get, True, 20)
                except queue.Empty:
                    # 订阅瞬间批次恰好跑完的窗口：超时先复探一次终态再发 ping，不留空转流
                    with Session(engine) as reprobe:
                        latest = reprobe.get(VideoBatch, batch_id)
                    if latest is not None and latest.status in _TERMINAL:
                        seq = (history[-1].get("seq", 0) + 1) if history else None
                        yield {"event": "stage", "data": json.dumps(_terminal_event(latest, seq), ensure_ascii=False)}
                        return
                    yield {"event": "ping", "data": "{}"}
                    continue
                if event["batch_id"] != batch_id or not _keep(event):
                    continue
                yield {"event": "stage", "data": json.dumps(event, ensure_ascii=False)}
                if _is_batch_terminal(event):
                    break
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(_stream())


@router.get("/videos/{video_id}")
def get_video(video_id: int, session: Session = Depends(get_session)):
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(404, "视频不存在")
    return {**_video_view(video), "batch_id": video.batch_id}


@router.get("/videos/{video_id}/transcript")
def transcript(video_id: int, session: Session = Depends(get_session)):
    if session.get(Video, video_id) is None:
        raise HTTPException(404, "视频不存在")
    # 1h 视频可达上千段；封顶 5000 段防巨型响应，前端在命中上限时提示（见 WorkbenchView）
    rows = session.exec(select(Segment).where(Segment.video_id == video_id)
                        .order_by(Segment.start_ms).limit(_TRANSCRIPT_LIMIT)).all()
    return [{"start_ms": r.start_ms, "end_ms": r.end_ms, "text": r.text} for r in rows]


@router.get("/settings/engines")
def engines():
    settings = get_settings()
    return {
        "asr": {
            "current": settings.asr_engine,
            "resolved": resolve_asr_name(settings.asr_engine),
            "available": ["auto", *available_asr()],
        },
        "ocr": {"current": settings.ocr_engine, "available": ["none", *available_ocr()]},
        "output_schemas": settings.output_schema_list,
        "cache_enabled": bool(settings.redis_url),
    }


def _save_engine_settings() -> None:
    """页 11 设置页持久化：写入 data/settings.json，重启由 main.py lifespan 读回。

    只落三个可改字段，不新增 ER 表——避免动 ER 图口径（docs/产品定义.md §六）。
    """
    settings = get_settings()
    path = Path(settings.media_root).parent / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 2,
        "asr_engine": settings.asr_engine,
        "ocr_engine": settings.ocr_engine,
        "output_schemas": settings.output_schemas,
    }, ensure_ascii=False), encoding="utf-8")


@router.put("/settings/engines")
def set_engines(body: dict):
    """页 11 设置页：OCR 引擎切换 + 默认产物集；校验后改运行时配置并持久化。"""
    settings = get_settings()
    if "asr" in body:
        if body["asr"] not in ["auto", *available_asr()]:
            raise HTTPException(422, f"未知 ASR 引擎，可选 {['auto', *available_asr()]}")
        settings.asr_engine = body["asr"]
    if "ocr" in body:
        if body["ocr"] != "none" and body["ocr"] not in available_ocr():
            raise HTTPException(422, f"未知 OCR 引擎，可选 {available_ocr()}")
        settings.ocr_engine = body["ocr"]
    if "output_schemas" in body:
        from app.artifacts import REGISTRY

        schemas = body["output_schemas"]
        if not isinstance(schemas, list):
            raise HTTPException(422, "产物集必须是数组")
        if not schemas:
            raise HTTPException(422, "至少保留一种产物类型")
        if any(not isinstance(s, str) for s in schemas):
            raise HTTPException(422, "产物类型必须是字符串")
        deduped = list(dict.fromkeys(s.strip() for s in schemas if s.strip()))
        if not deduped:
            raise HTTPException(422, "至少保留一种产物类型")
        unknown = [s for s in deduped if s not in REGISTRY]
        if unknown:
            raise HTTPException(422, f"未知产物类型 {unknown}")
        settings.output_schemas = ",".join(deduped)
    _save_engine_settings()
    return engines()
