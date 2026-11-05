"""垂直切片自检：不装任何引擎也能跑通「转写 → 结构化 → 产物 → 落库 → 导出」。"""

from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import engine, init_db
from app.enums import ArtifactType, RevisionState, StageStatus, VideoStatus
from app.export import build_batch_markdown
from app.models import Artifact, Evidence, KnowledgeItem, Segment, Video, VideoBatch
from app.pipeline import parse_video, retry_video
from app.routers.knowledge import _brief


@pytest.fixture(scope="module", autouse=True)
def _db():
    init_db()


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
