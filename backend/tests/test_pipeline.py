"""垂直切片自检：不装任何引擎也能跑通「转写 → 结构化 → 产物 → 落库 → 导出」。"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.artifacts import ItemDraft
from app.db import engine, init_db
from app.enums import ArtifactType, BatchStatus, Confidence, RevisionState, StageStatus, VideoStatus
from app.export import build_batch_markdown, ts
from app.models import Artifact, ConflictRecord, Evidence, KnowledgeItem, Segment, Video, VideoBatch
from app.pipeline import ProgressBus, _persist, parse_batch, parse_video, recover_orphan_runs, retry_video
from app.routers.knowledge import _brief


@pytest.fixture(scope="module", autouse=True)
def _db():
    init_db()


def test_progress_bus_history_is_bounded_and_reset_keeps_seq():
    """历史最多 256 条；reset 清历史但 seq 继续递增，避免在线订阅者去重误吞新事件。"""
    bus = ProgressBus()
    _, empty = bus.subscribe(42)
    assert empty == []
    for _ in range(300):
        bus.emit(42, None, "batch", "running")
    _, hist = bus.subscribe(42)
    assert len(hist) == 256
    assert hist[0]["seq"] == 45 and hist[-1]["seq"] == 300

    bus.reset(42)
    _, cleared = bus.subscribe(42)
    assert cleared == []
    bus.emit(42, None, "batch", "succeeded")
    _, after_reset = bus.subscribe(42)
    assert after_reset[-1]["seq"] == 301

    bus.forget(42)
    bus.emit(42, None, "batch", "running")
    _, after_forget = bus.subscribe(42)
    assert after_forget[-1]["seq"] == 1


@pytest.fixture()
def video(tmp_path: Path) -> Video:
    """造一条批次里的视频；MockAsr 不读文件内容，只按文件名找样例转写。"""
    src = tmp_path / "vue3_lecture.mp4"
    src.write_bytes(b"\x00")
    with Session(engine) as session:
        batch = VideoBatch(name="测试批次", video_count=1)
        session.add(batch)
        session.commit()
        session.refresh(batch)
        video = Video(batch_id=batch.id, path=str(src))
        session.add(video)
        session.commit()
        session.refresh(video)
        return video


def test_parse_video_produces_evidenced_items(video: Video):
    with Session(engine) as session:
        parsed = parse_video(session, session.get(Video, video.id))

        assert parsed.duration_ms > 0
        assert parsed.transcribe_status == StageStatus.DONE
        assert parsed.visual_status == StageStatus.SKIPPED   # OCR 关闭 → 降级，对应页 12
        assert parsed.status == VideoStatus.SUCCEEDED

        assert len(session.exec(select(Segment).where(Segment.video_id == parsed.id)).all()) == 13

        items = session.exec(select(KnowledgeItem).where(KnowledgeItem.video_id == parsed.id)).all()
        types = {i.type for i in items}
        assert ArtifactType.SUMMARY in types
        assert ArtifactType.UML_DRAFT in types
        assert ArtifactType.KEY_POINTS in types

        for item in items:
            assert item.evidence_id, "每条结论都必须挂证据，否则 F1 溯源不成立"
            ev = session.get(Evidence, item.evidence_id)
            assert ev.quote
        assert session.exec(select(Artifact).where(
            Artifact.item_id == items[0].id)).first() is not None


def test_export_markdown_carries_disclaimer_and_mermaid(video: Video):
    with Session(engine) as session:
        parse_video(session, session.get(Video, video.id))
        md = build_batch_markdown(session, video.batch_id)

    assert "识别结果仅供参考" in md
    assert "```mermaid" in md
    assert "flowchart TD" in md
    for banned in ("首次", "唯一", "100% 准确", "完全自动"):
        assert banned not in md, f"文档红线词出现在导出物里：{banned}"


def test_retry_single_video_does_not_touch_batch(video: Video):
    with Session(engine) as session:
        retry_video(session, video.id)
        again = session.get(Video, video.id)
        assert again.status in (VideoStatus.SUCCEEDED, VideoStatus.PARTIAL)
        assert again.transcribe_status == StageStatus.DONE


def test_reparse_is_idempotent_no_duplicate_rows(video: Video):
    """重试 / 整批重跑必须清空上次派生数据，否则转写与条目翻倍，导出也跟着重复。"""
    with Session(engine) as session:
        v = session.get(Video, video.id)
        parse_video(session, v)
        seg_first = len(session.exec(select(Segment).where(Segment.video_id == v.id)).all())
        items_first = len(session.exec(select(KnowledgeItem).where(KnowledgeItem.video_id == v.id)).all())

        parse_video(session, v)   # 同一条视频重跑一次

        assert len(session.exec(select(Segment).where(Segment.video_id == v.id)).all()) == seg_first
        items_second = session.exec(select(KnowledgeItem).where(KnowledgeItem.video_id == v.id)).all()
        assert len(items_second) == items_first
        assert len(session.exec(select(Evidence).where(Evidence.video_id == v.id)).all()) == items_first


def test_revision_state_machine_rejects_illegal_jump(video: Video):
    from fastapi import HTTPException
    from app.routers.knowledge import revise, RevisionIn

    with Session(engine) as session:
        parse_video(session, session.get(Video, video.id))
        item = session.exec(select(KnowledgeItem).where(
            KnowledgeItem.video_id == video.id)).first()
        with pytest.raises(HTTPException) as err:
            revise(item.id, RevisionIn(state=RevisionState.REVISED), session)
        assert err.value.status_code == 422

        ok = revise(item.id, RevisionIn(state=RevisionState.PENDING_CONFIRM), session)
        assert ok["state"] == "pending_confirm"


def test_brief_exposes_evidence_shape_for_frontend(video: Video):
    with Session(engine) as session:
        parse_video(session, session.get(Video, video.id))
        item = session.exec(select(KnowledgeItem).where(
            KnowledgeItem.video_id == video.id)).first()
        data = _brief(session, item)

    assert set(data) >= {"id", "type", "anchor_ms", "confidence", "evidence", "payload", "video_name"}
    assert data["evidence"]["channel"] in ("asr", "ocr", "both")


def test_conflict_record_anchors_to_nearest_item(video: Video):
    """F2 冲突记录应挂在离 source_a 时间点最近的条目上，而不是随手挂第一条。"""
    drafts = [
        ItemDraft(type=ArtifactType.KEY_POINTS, title="条目A", content="内容A",
                  confidence=Confidence.EXPLICIT, anchor_ms=1000, ordinal=0, quote="原话A"),
        ItemDraft(type=ArtifactType.KEY_POINTS, title="条目B", content="内容B",
                  confidence=Confidence.EXPLICIT, anchor_ms=60000, ordinal=1, quote="原话B"),
    ]
    conflicts = [SimpleNamespace(source_a_ms=55000, source_b_ms=2000, description="先讲A后改成B")]

    with Session(engine) as session:
        _persist(session, session.get(Video, video.id), drafts, conflicts, [])

        items = session.exec(select(KnowledgeItem).where(KnowledgeItem.video_id == video.id)).all()
        nearest = next(i for i in items if i.anchor_ms == 60000)
        record = session.exec(select(ConflictRecord).where(
            ConflictRecord.item_id == nearest.id)).first()
        assert record is not None
        assert record.description == "先讲A后改成B"


def test_artifact_stage_exception_marks_batch_failed(video: Video, monkeypatch):
    """阶段④异常不能让批次永久 RUNNING。"""
    monkeypatch.setattr("app.pipeline.resolve", lambda names: (_ for _ in ()).throw(RuntimeError("产物策略炸了")))
    with Session(engine) as session:
        parse_batch(session, session.get(VideoBatch, video.batch_id))
        batch = session.get(VideoBatch, video.batch_id)
        parsed = session.get(Video, video.id)
    assert batch.status == BatchStatus.FAILED
    assert parsed.status == VideoStatus.FAILED
    assert parsed.artifact_status == StageStatus.FAILED
    assert "产物策略炸了" in parsed.error


def test_parse_batch_survives_unexpected_video_exception(video: Video, monkeypatch):
    monkeypatch.setattr("app.pipeline.parse_video", lambda session, v: (_ for _ in ()).throw(RuntimeError("视频级异常")))
    with Session(engine) as session:
        parse_batch(session, session.get(VideoBatch, video.batch_id))
        batch = session.get(VideoBatch, video.batch_id)
        parsed = session.get(Video, video.id)
    assert batch.status == BatchStatus.FAILED
    assert parsed.status == VideoStatus.FAILED
    assert "视频级异常" in parsed.error


def test_retry_recomputes_batch_status(video: Video, monkeypatch):
    """先让结构阶段失败，再恢复重试：批次必须从 failed 重算为 succeeded。"""
    monkeypatch.setattr("app.pipeline.structure",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("LLM 暂时不可用")))
    with Session(engine) as session:
        parse_video(session, session.get(Video, video.id))
        assert session.get(Video, video.id).status == VideoStatus.FAILED
    monkeypatch.undo()
    with Session(engine) as session:
        retry_video(session, video.id)
        batch = session.get(VideoBatch, video.batch_id)
        parsed = session.get(Video, video.id)
    assert parsed.status == VideoStatus.SUCCEEDED
    assert batch.status == BatchStatus.SUCCEEDED


def test_recover_orphan_runs_marks_running_failed(video: Video):
    with Session(engine) as session:
        batch = session.get(VideoBatch, video.batch_id)
        parsed = session.get(Video, video.id)
        batch.status = BatchStatus.RUNNING
        parsed.status = VideoStatus.RUNNING
        parsed.transcribe_status = StageStatus.RUNNING
        session.add(batch)
        session.add(parsed)
        session.commit()

        recover_orphan_runs(session)
        batch = session.get(VideoBatch, video.batch_id)
        parsed = session.get(Video, video.id)
    assert parsed.status == VideoStatus.FAILED
    assert parsed.transcribe_status == StageStatus.FAILED
    assert "服务重启" in parsed.error
    assert batch.status == BatchStatus.FAILED


def test_export_timestamp_over_hour():
    assert ts(3_725_000) == "1:02:05"


def test_export_empty_batch_has_explicit_notice():
    with Session(engine) as session:
        batch = VideoBatch(name="空批次", video_count=0, status=BatchStatus.FAILED)
        session.add(batch)
        session.commit()
        session.refresh(batch)
        md = build_batch_markdown(session, batch.id)
    assert "未产出任何条目" in md


def test_export_formats_conflict_sources_as_timestamps(video: Video):
    with Session(engine) as session:
        parse_video(session, session.get(Video, video.id))
        item = session.exec(select(KnowledgeItem).where(
            KnowledgeItem.video_id == video.id)).first()
        session.add(ConflictRecord(item_id=item.id, source_a="12000ms", source_b="90000ms",
                                   description="前后表述不一致"))
        session.commit()
        md = build_batch_markdown(session, video.batch_id)
    assert "0:12" in md and "1:30" in md
    assert "12000ms" not in md


def test_sanitize_error_strips_local_paths():
    """错误文本上 UI 前必须洗掉本机路径（事件流/进度页不暴露落盘路径的约定）。"""
    from app.pipeline import sanitize_error

    msg = sanitize_error(r"模型加载失败：C:\Users\lenovo\AppData\Local\Temp\xyz\model.bin 缺失")
    assert "C:" not in msg and "本机路径" in msg
    msg2 = sanitize_error("帧写入失败 /tmp/yueying-123/frame.jpg 不可读")
    assert "/tmp/" not in msg2 and "本机路径" in msg2
    assert sanitize_error("普通错误信息保持原样") == "普通错误信息保持原样"
    assert sanitize_error("") == ""


def test_whisper_cache_key_tracks_model_size(monkeypatch):
    """v0.16：whisper 模型档位必须参与缓存键，tiny/base 不得命中彼此的缓存。"""
    from types import SimpleNamespace

    from app.pipeline import _asr_cache_name

    monkeypatch.setenv("VMIND_WHISPER_MODEL", "tiny")
    tiny = _asr_cache_name(SimpleNamespace(name="whisper", cache_variant="tiny"))
    monkeypatch.setenv("VMIND_WHISPER_MODEL", "base")
    base = _asr_cache_name(SimpleNamespace(name="whisper", cache_variant="base"))
    mock = _asr_cache_name(SimpleNamespace(name="mock"))
    assert tiny != base, "换档位后不得复用旧缓存"
    assert mock == "asr:mock", "无档位概念的引擎保持原键格式"
