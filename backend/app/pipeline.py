"""垂直切片主链路：四阶段顺序解析 + 单条重试 + 进度事件。

范围口径（docs/交付与排期.md §三）：顺序处理，不做并发调度与队列持久化；
失败只影响单条，批次进 PARTIAL，重试只重跑这一条。
"""

import queue
import shutil
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete
from sqlmodel import Session, select

from app import cache
from app.artifacts import ItemDraft, ParseContext, resolve
from app.config import Settings, get_settings
from app.enums import (
    STAGES,
    BatchStatus,
    RevisionState,
    Stage,
    StageStatus,
    TagTarget,
    VideoStatus,
)
from app.engines.base import AsrEngine, KeyFrame, OcrEngine, build_asr, build_ocr
from app.llm import structure
from app.models import (
    Artifact,
    ConflictRecord,
    Evidence,
    KnowledgeItem,
    Note,
    Revision,
    Segment,
    Tag,
    TagBinding,
    Video,
    VideoBatch,
)


class ProgressBus:
    """内存事件总线，供 SSE 订阅。进程重启即丢——队列持久化明确在范围外。"""

    def __init__(self) -> None:
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def emit(self, batch_id: int, video_id: int | None, stage: str, status: str, message: str = "") -> None:
        event = {
            "batch_id": batch_id, "video_id": video_id, "stage": stage, "status": status,
            "message": message, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._lock:
            for q in list(self._subs):
                if q.full():
                    continue
                q.put(event)


bus = ProgressBus()


def _set_stage(session: Session, video: Video, stage: Stage, status: StageStatus, error: str = "") -> None:
    setattr(video, f"{stage.value}_status", status)
    if error:
        # 多个阶段可能先后失败：累加而不是覆盖，失败定位以阶段状态为准
        video.error = f"{video.error}\n{error}".strip()[:500]
    session.add(video)
    session.commit()
    bus.emit(video.batch_id, video.id, stage.value, status.value, error)


def _transcript_rows(session: Session, video_id: int) -> list[tuple[int, int, str]]:
    rows = session.exec(select(Segment).where(Segment.video_id == video_id)).all()
    return [(r.start_ms, r.end_ms, r.text) for r in rows]


def _localize_frames(video_id: int, frames: list[KeyFrame]) -> list[KeyFrame]:
    """把引擎产出的关键帧复制进 media_root/frames/{video_id}/，返回稳定路径。

    输入输出都是本机绝对路径（画面通道 OCR 还要直接读文件）；入库时经 _media_url
    转成 /media URL。yueying 默认把帧写在临时目录，不复制的话 /media 不可达，
    进程重启后缓存里的旧路径也会失效。缓存里存的即这里的稳定路径。
    """
    if not frames:
        return frames
    root = Path(get_settings().media_root) / "frames" / str(video_id)
    root.mkdir(parents=True, exist_ok=True)
    out: list[KeyFrame] = []
    for i, frame in enumerate(frames):
        src = Path(frame.path)
        if not src.exists():
            continue   # 缓存命中但帧文件已被清理：丢这一帧，画面通道会自行降级
        dest = root / f"frame_{frame.ms}_{i}{src.suffix.lower() or '.jpg'}"
        if not dest.exists():
            shutil.copyfile(src, dest)
        out.append(KeyFrame(ms=frame.ms, path=str(dest)))
    return out


def _media_url(frame_path: str, settings: Settings) -> str:
    """media_root 下的绝对路径 → /media URL；不在 media_root 下则返回空，前端按无帧处理。"""
    if not frame_path:
        return ""
    try:
        rel = Path(frame_path).resolve().relative_to(Path(settings.media_root).resolve())
    except ValueError:
        return ""
    return f"/media/{rel.as_posix()}"


def _clear_video_data(session: Session, video_id: int) -> None:
    """重跑前清空上次解析的派生数据，保证重试 / 整批重解析幂等，不产生重复条目。

    删除顺序按外键依赖：绑定与子表在前，KnowledgeItem 在 Note 之后，Evidence/Segment 最后。
    Tag 本体跨视频共享，保留；条目上的 Note 随条目一起清（锚点指向的条目已不存在）。
    """
    item_ids = session.exec(select(KnowledgeItem.id).where(KnowledgeItem.video_id == video_id)).all()
    if item_ids:
        session.exec(delete(TagBinding).where(
            TagBinding.target_type == TagTarget.ITEM, TagBinding.target_id.in_(item_ids)))
        session.exec(delete(ConflictRecord).where(ConflictRecord.item_id.in_(item_ids)))
        session.exec(delete(Revision).where(Revision.item_id.in_(item_ids)))
        session.exec(delete(Artifact).where(Artifact.item_id.in_(item_ids)))
        session.exec(delete(Note).where(Note.item_id.in_(item_ids)))
        session.exec(delete(KnowledgeItem).where(KnowledgeItem.video_id == video_id))
    session.exec(delete(Evidence).where(Evidence.video_id == video_id))
    session.exec(delete(Segment).where(Segment.video_id == video_id))
    session.commit()


def parse_video(session: Session, video: Video, settings: Settings | None = None) -> Video:
    settings = settings or get_settings()
    video.status = VideoStatus.RUNNING
    video.error = ""
    session.add(video)
    session.commit()

    _clear_video_data(session, video.id)   # 幂等入口：重试/重跑不残留上次的转写与条目

    asr: AsrEngine = build_asr(settings.asr_engine)
    ocr: OcrEngine | None = build_ocr(settings.ocr_engine)

    frames: list[KeyFrame] = []
    frame_texts: list[FrameText] = []

    # ① 音频通道
    _set_stage(session, video, Stage.TRANSCRIBE, StageStatus.RUNNING)
    try:
        cache_key = cache.key_of(video.path, f"asr:{asr.name}")
        hit = cache.get(cache_key)
        if hit:
            from app.engines.base import AsrResult, TranscriptSegment

            result = AsrResult(
                duration_ms=hit["duration_ms"],
                segments=[TranscriptSegment(**s) for s in hit["segments"]],
                frames=[KeyFrame(**f) for f in hit.get("frames", [])],
            )
        else:
            result = asr.transcribe(video.path)

        # 关键帧复制进 media_root 后再落缓存：临时目录的帧 /media 不可达，重启后旧路径也会失效
        result.frames = _localize_frames(video.id, result.frames)
        if not hit:
            cache.put(cache_key, asdict(result))

        for seg in result.segments:
            session.add(Segment(video_id=video.id, start_ms=seg.start_ms, end_ms=seg.end_ms, text=seg.text))
        frames = result.frames
        if video.duration_ms == 0:
            video.duration_ms = result.duration_ms
        _set_stage(session, video, Stage.TRANSCRIBE, StageStatus.DONE)
    except Exception as exc:
        _set_stage(session, video, Stage.TRANSCRIBE, StageStatus.FAILED, str(exc))
        video.status = VideoStatus.FAILED
        session.add(video)
        session.commit()
        return video

    # ② 画面通道（OCR 关闭或无关键帧时降级为 SKIPPED，对应页 12 异常态）
    if ocr is None or not frames:
        _set_stage(session, video, Stage.VISUAL, StageStatus.SKIPPED, "画面通道未启用或无关键帧")
    else:
        _set_stage(session, video, Stage.VISUAL, StageStatus.RUNNING)
        try:
            frame_texts = ocr.recognize(frames)
            _set_stage(session, video, Stage.VISUAL, StageStatus.DONE)
        except Exception as exc:
            frame_texts = []
            _set_stage(session, video, Stage.VISUAL, StageStatus.FAILED, str(exc))

    # ③ LLM 结构化
    _set_stage(session, video, Stage.STRUCTURE, StageStatus.RUNNING)
    transcript = _transcript_rows(session, video.id)
    try:
        draft = structure(transcript, [(f.ms, f.text) for f in frame_texts], video.duration_ms)
        _set_stage(session, video, Stage.STRUCTURE, StageStatus.DONE)
    except Exception as exc:
        _set_stage(session, video, Stage.STRUCTURE, StageStatus.FAILED, str(exc))
        video.status = VideoStatus.FAILED
        session.add(video)
        session.commit()
        return video

    # ④ 产物生成与落库
    _set_stage(session, video, Stage.ARTIFACT, StageStatus.RUNNING)
    ctx = ParseContext(draft=draft, segments=list(result.segments), frames=frames,
                       ocr=frame_texts, duration_ms=video.duration_ms)
    drafts: list[ItemDraft] = []
    for strategy in resolve(settings.output_schema_list):
        drafts.extend(strategy.build(ctx))
    _persist(session, video, drafts, draft.conflicts, draft.tags)

    failed = any(getattr(video, f"{s.value}_status") == StageStatus.FAILED for s in STAGES)
    video.status = VideoStatus.PARTIAL if failed else VideoStatus.SUCCEEDED
    session.add(video)
    session.commit()
    _set_stage(session, video, Stage.ARTIFACT, StageStatus.DONE)
    return video


def _persist(session: Session, video: Video, drafts: list[ItemDraft],
             conflicts, tags: list[str]) -> None:
    settings = get_settings()
    for d in drafts:
        evidence = Evidence(
            video_id=video.id,
            start_ms=d.anchor_ms,
            end_ms=min(d.anchor_ms + 5000, video.duration_ms or d.anchor_ms + 5000),
            quote=d.quote,
            frame_path=_media_url(d.frame_path, settings),
            channel=d.channel,
        )
        session.add(evidence)
        session.commit()
        session.refresh(evidence)

        item = KnowledgeItem(
            video_id=video.id, type=d.type, title=d.title, content=d.content,
            confidence=d.confidence, anchor_ms=d.anchor_ms, evidence_id=evidence.id, ordinal=d.ordinal,
        )
        session.add(item)
        session.commit()
        session.refresh(item)

        session.add(Artifact(item_id=item.id, schema_type=d.type, payload=d.payload))
        session.add(Revision(item_id=item.id, state=RevisionState.DRAFT, snapshot=item.content))

        for name in d.tags:
            _bind_tag(session, TagTarget.ITEM, item.id, name, suggested_by_ai=True)

    if conflicts:
        # 冲突记录挂到离 source_a 时间点最近的条目上，而不是随手挂在第一条
        items = session.exec(select(KnowledgeItem).where(KnowledgeItem.video_id == video.id)).all()
        for c in conflicts:
            if not items:
                break
            target = min(items, key=lambda it: abs(it.anchor_ms - c.source_a_ms))
            session.add(ConflictRecord(
                item_id=target.id, source_a=f"{c.source_a_ms}ms", source_b=f"{c.source_b_ms}ms",
                description=c.description))
    for name in tags:
        _bind_tag(session, TagTarget.VIDEO, video.id, name, suggested_by_ai=True)
    session.commit()


def _bind_tag(session: Session, target_type: TagTarget, target_id: int, name: str,
              suggested_by_ai: bool) -> None:
    name = name.strip()
    if not name:
        return
    tag = session.exec(select(Tag).where(Tag.name == name)).first()
    if tag is None:
        tag = Tag(name=name, suggested_by_ai=suggested_by_ai)
        session.add(tag)
        session.commit()
        session.refresh(tag)
    exists = session.exec(select(TagBinding).where(
        TagBinding.tag_id == tag.id, TagBinding.target_type == target_type,
        TagBinding.target_id == target_id)).first()
    if exists is None:
        session.add(TagBinding(tag_id=tag.id, target_type=target_type, target_id=target_id))


def parse_batch(session: Session, batch: VideoBatch) -> None:
    """顺序处理整批（范围外：并发调度）。"""
    batch.status = BatchStatus.RUNNING
    session.add(batch)
    session.commit()
    bus.emit(batch.id, None, "batch", StageStatus.RUNNING.value)

    videos = session.exec(select(Video).where(Video.batch_id == batch.id)).all()
    for video in videos:
        bus.emit(batch.id, video.id, "batch", "video_start", video.path)
        parse_video(session, video)

    statuses = [v.status for v in videos]
    if all(s == VideoStatus.SUCCEEDED for s in statuses):
        batch.status = BatchStatus.SUCCEEDED
    elif any(s in (VideoStatus.SUCCEEDED, VideoStatus.PARTIAL) for s in statuses):
        batch.status = BatchStatus.PARTIAL
    else:
        batch.status = BatchStatus.FAILED
    session.add(batch)
    session.commit()
    bus.emit(batch.id, None, "batch", batch.status.value)


def retry_video(session: Session, video_id: int) -> Video | None:
    video = session.get(Video, video_id)
    if video is None:
        return None
    for stage in STAGES:
        setattr(video, f"{stage.value}_status", StageStatus.PENDING)
    session.add(video)
    session.commit()
    return parse_video(session, video)
