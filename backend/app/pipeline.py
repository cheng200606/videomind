"""垂直切片主链路：四阶段顺序解析 + 单条重试 + 进度事件。

范围口径（docs/交付与排期.md §三）：顺序处理，不做并发调度与队列持久化；
失败只影响单条，批次进 PARTIAL，重试只重跑这一条。
"""

import queue
import re
import shutil
import threading
from collections import OrderedDict, deque
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
from app.engines.frames import FRAME_INTERVAL_S, sample_frames
from app.llm import structure
from app.media import display_name
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
    """内存事件总线，供 SSE 订阅。进程重启即丢——队列持久化明确在范围外。

    每个批次保留最近 256 条事件：进度页刷新后订阅仍能回放本次运行的事件，
    而不是只剩一条终态。全局最多保留 64 个批次，避免长期运行内存无界增长。
    """

    HISTORY_LIMIT = 256
    BATCH_LIMIT = 64

    def __init__(self) -> None:
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._history: OrderedDict[int, deque[dict]] = OrderedDict()
        self._seq: dict[int, int] = {}

    def subscribe(self, batch_id: int) -> tuple[queue.Queue, list[dict]]:
        """先注册队列再复制历史，保证订阅瞬间不会漏掉并发 emit 的事件。"""
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._lock:
            self._subs.append(q)
            hist = self._history.get(batch_id)
            if hist is not None:
                self._history.move_to_end(batch_id)
            snapshot = list(hist) if hist is not None else []
        return q, snapshot

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def reset(self, batch_id: int) -> None:
        """重跑/重试前清空历史，但保留 seq 单调递增——在线订阅者的去重集合不会误吞新事件。"""
        with self._lock:
            self._history.pop(batch_id, None)

    def forget(self, batch_id: int) -> None:
        """批次删除后彻底清理；SQLite 可能复用主键，不能把旧事件回放给新批次。"""
        with self._lock:
            self._history.pop(batch_id, None)
            self._seq.pop(batch_id, None)

    def emit(self, batch_id: int, video_id: int | None, stage: str, status: str, message: str = "") -> None:
        with self._lock:
            seq = self._seq.get(batch_id, 0) + 1
            self._seq[batch_id] = seq
            event = {
                "batch_id": batch_id, "video_id": video_id, "stage": stage, "status": status,
                "message": message, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "seq": seq,
            }
            hist = self._history.get(batch_id)
            if hist is None:
                hist = deque(maxlen=self.HISTORY_LIMIT)
                self._history[batch_id] = hist
                while len(self._history) > self.BATCH_LIMIT:
                    self._history.popitem(last=False)
            hist.append(event)
            self._history.move_to_end(batch_id)
            for q in list(self._subs):
                if q.full():
                    continue
                q.put(event)


bus = ProgressBus()


_WIN_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"'，。）)）]*")
_POSIX_PATH_RE = re.compile(r"/(?:home|Users|tmp|var|root|data)[^\s\"'，。）)]*")


def sanitize_error(text: str, limit: int = 300) -> str:
    """错误文本要上 UI（进度页/SSE/事件流）：剥掉本机绝对路径与控制字符，只留可读原因。

    引擎异常常携带临时目录、模型文件等本机路径（如 FileNotFoundError 的完整路径），
    与「事件流不暴露落盘路径」的约定冲突，这里统一在写入点清洗。
    """
    if not text:
        return ""
    cleaned = _WIN_PATH_RE.sub("(本机路径)", text)
    cleaned = _POSIX_PATH_RE.sub("(本机路径)", cleaned)
    cleaned = "".join(ch for ch in cleaned if ch == "\n" or ch.isprintable())
    return re.sub(r"\n{2,}", "\n", cleaned).strip()[:limit]


class ParseMutex:
    """同一时间只允许一个批次在解析——「顺序处理，不做并发调度」口径的显式化。

    两个批次并发解析在 SQLite 下会撞写锁（database locked），先完成的
    _recompute_batch_status 还会把仍在解析的批次提前置终态。进程级守护即可：
    后台线程与请求都在同一进程；进程重启后集合自然为空，孤儿恢复由
    recover_orphan_runs 兜底（ RUNNING 状态会被标失败，可重试）。
    """

    def __init__(self) -> None:
        self._active: set[int] = set()
        self._lock = threading.Lock()

    def claim(self, batch_id: int) -> bool:
        with self._lock:
            if self._active:
                return False
            self._active.add(batch_id)
            return True

    def release(self, batch_id: int) -> None:
        with self._lock:
            self._active.discard(batch_id)


parse_mutex = ParseMutex()


def _set_stage(session: Session, video: Video, stage: Stage, status: StageStatus, error: str = "") -> None:
    setattr(video, f"{stage.value}_status", status)
    if error and status == StageStatus.FAILED:
        # 多个阶段可能先后失败：累加而不是覆盖，失败定位以阶段状态为准；
        # SKIPPED 的说明（如“画面通道未启用”）只是降级原因，不该伪装成错误
        error = sanitize_error(error)
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


def _keyframes(video: Video) -> list[KeyFrame]:
    """Whisper/FunASR 只产转写不出帧：画面通道启用时用 av 独立抽样补齐关键帧。

    结果走独立缓存（键含采样间隔），与 ASR 缓存互不影响；抽样失败只让画面通道
    降级为 SKIPPED，不能拖垮整条解析。缓存存的是 localize 后的稳定路径。
    """
    cache_key = cache.key_of(video.path, f"frames:{FRAME_INTERVAL_S:g}")
    hit = cache.get(cache_key)
    if hit is not None:
        return [KeyFrame(**f) for f in hit]
    try:
        frames = sample_frames(video.path, FRAME_INTERVAL_S)
    except Exception:
        return []
    if not frames:
        return []
    frames = _localize_frames(video.id, frames)
    cache.put(cache_key, [asdict(f) for f in frames])
    return frames


def _clear_derived_items(session: Session, video_id: int) -> None:
    """清掉一条视频的条目派生数据与证据，但保留 Segment（阶段④失败时仍可回看转写）。"""
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
    session.commit()


def _clear_video_data(session: Session, video_id: int) -> None:
    """重跑前清空上次解析的派生数据，保证重试 / 整批重解析幂等，不产生重复条目。

    删除顺序按外键依赖：绑定与子表在前，KnowledgeItem 在 Note 之后，Evidence/Segment 最后。
    Tag 本体跨视频共享，保留；条目上的 Note 随条目一起清（锚点指向的条目已不存在）。
    """
    _clear_derived_items(session, video_id)
    session.exec(delete(Segment).where(Segment.video_id == video_id))
    session.commit()


def _recompute_batch_status(session: Session, batch_id: int) -> BatchStatus:
    """按视频终态重算批次状态；重试/重跑后必须调用，避免批次状态停在旧值。"""
    batch = session.get(VideoBatch, batch_id)
    if batch is None:
        return BatchStatus.FAILED
    statuses = [v.status for v in session.exec(select(Video).where(Video.batch_id == batch_id)).all()]
    if not statuses:
        status = BatchStatus.FAILED
    elif all(s == VideoStatus.SUCCEEDED for s in statuses):
        status = BatchStatus.SUCCEEDED
    elif any(s in (VideoStatus.SUCCEEDED, VideoStatus.PARTIAL) for s in statuses):
        status = BatchStatus.PARTIAL
    else:
        status = BatchStatus.FAILED
    batch.status = status
    session.add(batch)
    session.commit()
    return status


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

        # Whisper 等纯音频引擎不出帧：画面通道启用时用 av 独立抽样补齐（失败只降级）
        if ocr is not None and not result.frames:
            result.frames = _keyframes(video)

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

    # ③ LLM 结构化（长转写按段边界分块逐段调用，见 llm.structure）
    _set_stage(session, video, Stage.STRUCTURE, StageStatus.RUNNING)
    transcript = _transcript_rows(session, video.id)
    notices: list[str] = []

    def _structure_progress(i: int, n: int) -> None:
        if n > 1:
            bus.emit(video.batch_id, video.id, Stage.STRUCTURE.value,
                     StageStatus.RUNNING.value, f"结构化 {i}/{n} 段")

    try:
        report: dict = {}
        draft = structure(transcript, [(f.ms, f.text) for f in frame_texts],
                          video.duration_ms, report=report, progress=_structure_progress)
        failed_chunks = report.get("failed_chunks") or []
        if failed_chunks:
            notices.append(f"第 {'、'.join(str(i) for i in failed_chunks)} 段结构化失败，对应区间内容可能缺失")
        elif report.get("transcript_truncated"):
            # 单段超长的物理截断：诚实边界，不能静默
            notices.append(f"转写单段超长（约 {report.get('transcript_chars', 0)} 字符），超限部分未能参与结构化")
        if (report.get("chunk_count") or 1) > 1 and not failed_chunks:
            notices.append(f"转写较长，已按时间切 {report['chunk_count']} 段完整结构化")

        if failed_chunks:
            # 内容真缺了一块：阶段置 PARTIAL，视频随之 PARTIAL，比「成功但缺内容」诚实
            _set_stage(session, video, Stage.STRUCTURE, StageStatus.PARTIAL, notices[0])
            for extra in notices[1:]:
                bus.emit(video.batch_id, video.id, Stage.STRUCTURE.value, StageStatus.PARTIAL.value, extra)
        else:
            for notice in notices:
                bus.emit(video.batch_id, video.id, Stage.STRUCTURE.value, StageStatus.DONE.value, notice)
            _set_stage(session, video, Stage.STRUCTURE, StageStatus.DONE)
    except Exception as exc:
        _set_stage(session, video, Stage.STRUCTURE, StageStatus.FAILED, str(exc))
        video.status = VideoStatus.FAILED
        session.add(video)
        session.commit()
        return video

    # ④ 产物生成与落库
    _set_stage(session, video, Stage.ARTIFACT, StageStatus.RUNNING)
    try:
        ctx = ParseContext(draft=draft, segments=list(result.segments), frames=frames,
                           ocr=frame_texts, duration_ms=video.duration_ms,
                           notices=notices)
        drafts: list[ItemDraft] = []
        for strategy in resolve(settings.output_schema_list):
            drafts.extend(strategy.build(ctx))
        _persist(session, video, drafts, draft.conflicts, draft.tags)
    except Exception as exc:
        # 阶段④异常不能穿出后台任务：批次会永久 RUNNING、无法删除，SSE 也只剩余 ping
        session.rollback()
        video = session.get(Video, video.id)
        if video is None:
            raise
        _clear_derived_items(session, video.id)
        video.status = VideoStatus.FAILED
        session.add(video)
        session.commit()
        _set_stage(session, video, Stage.ARTIFACT, StageStatus.FAILED, str(exc))
        return video

    # 阶段 PARTIAL（如结构化只成功了一部分）与 FAILED 一样，都算「产物不完整」
    bad = (StageStatus.FAILED, StageStatus.PARTIAL)
    failed = any(getattr(video, f"{s.value}_status") in bad for s in STAGES)
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


def _emit_video_terminal(batch_id: int, video: Video) -> None:
    """单条视频终态事件：stage=batch 但 video_id 非空，前端据此实时更新矩阵。

    批次终态仍是 video_id=None；SSE 消费者必须用 video_id 区分，避免把单条结束当成整批结束。
    """
    bus.emit(batch_id, video.id, "batch", video.status.value,
             display_name(video.path, video.batch_id))


def parse_batch(session: Session, batch: VideoBatch) -> None:
    """顺序处理整批（范围外：并发调度）。任何异常都必须让批次落终态。"""
    bus.reset(batch.id)   # 新一次运行不把上一次的事件回放给刷新页面的人
    batch.status = BatchStatus.RUNNING
    session.add(batch)
    session.commit()
    bus.emit(batch.id, None, "batch", StageStatus.RUNNING.value)

    videos = session.exec(select(Video).where(Video.batch_id == batch.id).order_by(Video.id)).all()
    try:
        for video in videos:
            # 事件流面向使用者，只给文件名——本机绝对路径不该上 UI
            bus.emit(batch.id, video.id, "batch", "video_start",
                     display_name(video.path, video.batch_id))
            try:
                done = parse_video(session, video)
                _emit_video_terminal(batch.id, done)
            except Exception as exc:
                # 单条未预期异常不能拖垮整批：标失败后继续下一条
                session.rollback()
                failed = session.get(Video, video.id)
                if failed is not None:
                    failed.status = VideoStatus.FAILED
                    failed.error = f"{failed.error}\n{type(exc).__name__}: {sanitize_error(str(exc))}".strip()[:500]
                    session.add(failed)
                    session.commit()
                    _emit_video_terminal(batch.id, failed)
    finally:
        status = _recompute_batch_status(session, batch.id)
        bus.emit(batch.id, None, "batch", status.value)


def retry_video(session: Session, video_id: int) -> Video | None:
    video = session.get(Video, video_id)
    if video is None:
        return None
    batch_id = video.batch_id
    bus.reset(batch_id)
    for stage in STAGES:
        setattr(video, f"{stage.value}_status", StageStatus.PENDING)
    session.add(video)
    session.commit()
    bus.emit(batch_id, video.id, "batch", "video_start",
             display_name(video.path, video.batch_id))
    try:
        result = parse_video(session, video)
        if result is not None:
            _emit_video_terminal(batch_id, result)
    except Exception as exc:
        session.rollback()
        failed = session.get(Video, video_id)
        if failed is not None:
            failed.status = VideoStatus.FAILED
            failed.error = f"{failed.error}\n{type(exc).__name__}: {sanitize_error(str(exc))}".strip()[:500]
            session.add(failed)
            session.commit()
            _emit_video_terminal(batch_id, failed)
        result = failed
    finally:
        status = _recompute_batch_status(session, batch_id)
        bus.emit(batch_id, None, "batch", status.value)
    return result


def recover_orphan_runs(session: Session) -> None:
    """进程重启后把未完成的批次/视频标成失败，保证可重试、可删除。"""
    videos = session.exec(select(Video).where(
        Video.status.in_([VideoStatus.PENDING, VideoStatus.RUNNING]))).all()
    for video in videos:
        video.status = VideoStatus.FAILED
        video.error = f"{video.error}\n服务重启导致解析中断，可重试".strip()[:500]
        for stage in STAGES:
            if getattr(video, f"{stage.value}_status") == StageStatus.RUNNING:
                setattr(video, f"{stage.value}_status", StageStatus.FAILED)
        session.add(video)
    session.commit()

    batches = session.exec(select(VideoBatch).where(
        VideoBatch.status.in_([BatchStatus.PENDING, BatchStatus.RUNNING]))).all()
    for batch in batches:
        _recompute_batch_status(session, batch.id)
