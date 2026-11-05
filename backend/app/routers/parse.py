"""批次 / 上传 / 解析进度（页 2、页 3、页 12 异常态）。"""

import asyncio
import json
import queue
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.db import engine, get_session
from app.enums import STAGES, BatchStatus
from app.engines.base import available_asr, available_ocr
from app.models import Segment, Video, VideoBatch
from app.pipeline import bus, parse_batch, retry_video

router = APIRouter(prefix="/api", tags=["parse"])

_ALLOWED_SUFFIX = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
_TERMINAL = (BatchStatus.SUCCEEDED, BatchStatus.PARTIAL, BatchStatus.FAILED)
_TERMINAL_VALUES = tuple(s.value for s in _TERMINAL)


def _terminal_event(batch: VideoBatch) -> dict:
    """给「订阅前批次已结束」的重连者补一条终态事件，字段形状与 ProgressBus.emit 一致。"""
    return {
        "batch_id": batch.id, "video_id": None, "stage": "batch", "status": batch.status.value,
        "message": "", "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _run_batch(batch_id: int) -> None:
    """后台任务用独立会话——请求会话在响应返回时就关了。"""
    with Session(engine) as session:
        batch = session.get(VideoBatch, batch_id)
        if batch:
            parse_batch(session, batch)


@router.post("/batches", status_code=201)
async def create_batch(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    name: str = Form("未命名批次"),
    session: Session = Depends(get_session),
):
    settings = get_settings()
    root = Path(settings.media_root)
    root.mkdir(parents=True, exist_ok=True)

    batch = VideoBatch(name=name or "未命名批次", video_count=0, status=BatchStatus.PENDING)
    session.add(batch)
    session.commit()
    session.refresh(batch)

    seen: set[tuple[str, int]] = set()
    rejected: list[dict] = []
    for upload in files:
        filename = Path(upload.filename or "").name
        if Path(filename).suffix.lower() not in _ALLOWED_SUFFIX:
            rejected.append({"filename": filename, "reason": "不支持的格式，可选 mp4/mov/mkv/avi/webm"})
            continue
        dest = root / f"{batch.id}_{filename}"
        size = 0
        with dest.open("wb") as fh:                     # 分块落盘，大视频不整读进内存
            while chunk := await upload.read(1024 * 1024):
                fh.write(chunk)
                size += len(chunk)
        if (filename, size) in seen:                    # 批内同名同大小视为重复
            dest.unlink(missing_ok=True)
            rejected.append({"filename": filename, "reason": "与批内已有文件重复"})
            continue
        seen.add((filename, size))

        session.add(Video(batch_id=batch.id, path=str(dest)))
        batch.video_count += 1
    session.add(batch)
    session.commit()
    session.refresh(batch)

    background.add_task(_run_batch, batch.id)
    return {"id": batch.id, "name": batch.name, "video_count": batch.video_count, "rejected": rejected}


@router.get("/batches")
def list_batches(session: Session = Depends(get_session)):
    batches = session.exec(select(VideoBatch).order_by(VideoBatch.id.desc())).all()
    return [{
        "id": b.id, "name": b.name, "status": b.status.value,
        "video_count": b.video_count, "created_at": b.created_at,
    } for b in batches]


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, session: Session = Depends(get_session)):
    batch = session.get(VideoBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "批次不存在")
    videos = session.exec(select(Video).where(Video.batch_id == batch_id)).all()
    return {
        "id": batch.id, "name": batch.name, "status": batch.status.value,
        "videos": [{
            "id": v.id, "path": v.path, "duration_ms": v.duration_ms, "status": v.status.value,
            "error": v.error,
            "stages": {s.value: getattr(v, f"{s.value}_status").value for s in STAGES},
        } for v in videos],
    }


@router.post("/batches/{batch_id}/parse")
def reparse_batch(batch_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    if session.get(VideoBatch, batch_id) is None:
        raise HTTPException(404, "批次不存在")
    background.add_task(_run_batch, batch_id)
    return {"ok": True}


@router.post("/videos/{video_id}/retry")
def retry(video_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    """单条重试，不重跑整批（用例 3）。"""
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(404, "视频不存在")

    def _one(vid: int) -> None:
        with Session(engine) as s:
            retry_video(s, vid)

    background.add_task(_one, video_id)
    return {"ok": True}


@router.get("/batches/{batch_id}/progress", response_class=EventSourceResponse)
async def progress(batch_id: int):
    """批次进度 SSE。FastAPI 只有显式指定 EventSourceResponse 才走 text/event-stream 分支，
    否则生成器端点按 application/jsonl 输出，浏览器 EventSource 直接收不到。"""
    q = bus.subscribe()
    try:
        # 订阅前批次可能已经跑完（进度页刷新后重连），先探测终态，否则流只会空转 ping
        with Session(engine) as probe:
            batch = probe.get(VideoBatch, batch_id)
        if batch is not None and batch.status in _TERMINAL:
            yield {"event": "stage", "data": json.dumps(_terminal_event(batch), ensure_ascii=False)}
            return
        while True:
            try:
                event = await asyncio.to_thread(q.get, True, 20)
            except queue.Empty:
                yield {"event": "ping", "data": "{}"}
                continue
            if event["batch_id"] != batch_id:
                continue
            yield {"event": "stage", "data": json.dumps(event, ensure_ascii=False)}
            if event["stage"] == "batch" and event["status"] in _TERMINAL_VALUES:
                break
    finally:
        bus.unsubscribe(q)


@router.get("/videos/{video_id}")
def get_video(video_id: int, session: Session = Depends(get_session)):
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(404, "视频不存在")
    return {
        "id": video.id, "batch_id": video.batch_id, "path": video.path,
        "duration_ms": video.duration_ms, "status": video.status.value, "error": video.error,
        "stages": {s.value: getattr(video, f"{s.value}_status").value for s in STAGES},
    }


@router.get("/videos/{video_id}/transcript")
def transcript(video_id: int, session: Session = Depends(get_session)):
    rows = session.exec(select(Segment).where(Segment.video_id == video_id).order_by(Segment.start_ms)).all()
    return [{"start_ms": r.start_ms, "end_ms": r.end_ms, "text": r.text} for r in rows]


@router.get("/settings/engines")
def engines():
    settings = get_settings()
    return {
        "asr": {"current": settings.asr_engine, "available": available_asr()},
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
        "asr_engine": settings.asr_engine,
        "ocr_engine": settings.ocr_engine,
        "output_schemas": settings.output_schemas,
    }, ensure_ascii=False), encoding="utf-8")


@router.put("/settings/engines")
def set_engines(body: dict):
    """页 11 设置页：OCR 引擎切换 + 默认产物集；校验后改运行时配置并持久化。"""
    settings = get_settings()
    if "asr" in body:
        if body["asr"] not in available_asr():
            raise HTTPException(422, f"未知 ASR 引擎，可选 {available_asr()}")
        settings.asr_engine = body["asr"]
    if "ocr" in body:
        if body["ocr"] != "none" and body["ocr"] not in available_ocr():
            raise HTTPException(422, f"未知 OCR 引擎，可选 {available_ocr()}")
        settings.ocr_engine = body["ocr"]
    if "output_schemas" in body:
        from app.artifacts import REGISTRY

        unknown = [s for s in body["output_schemas"] if s not in REGISTRY]
        if unknown:
            raise HTTPException(422, f"未知产物类型 {unknown}")
        settings.output_schemas = ",".join(body["output_schemas"])
    _save_engine_settings()
    return engines()
