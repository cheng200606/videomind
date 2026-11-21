"""垂直切片自检：不装任何引擎也能跑通「转写 → 结构化 → 产物 → 落库 → 导出」。"""

from pathlib import Path
import json
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.artifacts import ItemDraft
from app.config import get_settings
from app.db import engine, init_db
from app.enums import ArtifactType, BatchStatus, Confidence, RevisionState, Stage, StageStatus, VideoStatus
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


def test_cache_key_is_content_addressed(tmp_path: Path):
    """同名同大小不同内容不能命中同一份缓存；不可读时回退不打断解析。"""
    from app.cache import key_of

    first = tmp_path / "a" / "lecture.mp4"
    second = tmp_path / "b" / "lecture.mp4"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"AAA" + b"\x00" * 4096)
    second.write_bytes(b"BBB" + b"\x00" * 4096)
    assert first.stat().st_size == second.stat().st_size

    k1 = key_of(str(first), "asr:mock")
    k2 = key_of(str(second), "asr:mock")
    assert k1 != k2, "内容不同必须换键，否则会拿到旧视频的转写/证据"
    assert key_of(str(first), "asr:mock") == k1, "同一文件同一引擎必须稳定命中"
    assert key_of(str(first), "asr:tiny") != k1, "引擎/档位仍参与键"
    assert key_of(str(tmp_path / "已不存在.mp4"), "asr:mock").startswith("vmind:asr:mock:")


def test_non_failed_stage_sanitizes_sse_error(video: Video):
    """非 FAILED 态（如 RUNNING 进度）也不能把本机绝对路径推给 SSE。"""
    from app.pipeline import _set_stage, bus

    raw = r"加载进度：C:\Users\lenovo\AppData\Local\Temp\model.bin 正在读取"
    q, _ = bus.subscribe(video.batch_id)
    try:
        with Session(engine) as session:
            current = session.get(Video, video.id)
            assert current is not None
            _set_stage(session, current, Stage.STRUCTURE, StageStatus.RUNNING, raw)
            assert "C:" not in current.error
        _, history = bus.subscribe(video.batch_id)
        message = history[-1]["message"]
        assert history[-1]["status"] == "running"
        assert "C:" not in message and "\\" not in message
        assert "本机路径" in message
    finally:
        bus.unsubscribe(q)


def test_fallback_notice_reaches_summary_and_export(video: Video):
    """无 Key 规则兜底必须随摘要 notice 进入工作台与导出文稿。"""
    from app import pipeline

    real_structure = pipeline.structure

    def structure_with_extra_notice(*args, **kwargs):
        # 同时触发一条既有 notice，验证 fallback 是追加而不是覆盖
        draft = real_structure(*args, **kwargs)
        kwargs["report"]["transcript_truncated"] = True
        return draft

    pipeline.structure = structure_with_extra_notice
    try:
        with Session(engine) as session:
            parsed = parse_video(session, session.get(Video, video.id))
            summary = session.exec(select(KnowledgeItem).where(
                KnowledgeItem.video_id == parsed.id,
                KnowledgeItem.type == ArtifactType.SUMMARY)).first()
            assert summary is not None
            artifact = session.exec(select(Artifact).where(
                Artifact.item_id == summary.id)).first()
            assert artifact is not None
            notice = str((artifact.payload or {}).get("notice") or "")
            assert "未调用大模型，条目为规则切分结果，仅供参考" in notice
            assert "转写单段超长" in notice, "既有 notice 不能被 fallback 覆盖"

            md = build_batch_markdown(session, video.batch_id)
            assert "未调用大模型，条目为规则切分结果，仅供参考" in md
    finally:
        pipeline.structure = real_structure


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


# ── v0.17 P0-2：零条目不许冒充成功（假成功收口）────────────────────────────


def test_normalize_schemas_reports_unknown_instead_of_dropping():
    """未知产物类型必须被挑出来交给调用方处理，不能在这里静默吞掉。"""
    from app.artifacts import REGISTRY, normalize_schemas

    valid, unknown = normalize_schemas([" summary ", "summary", "", "bogus", "key_points"])
    assert valid == ["summary", "key_points"], "去空白、保序去重"
    assert unknown == ["bogus"], "未知项必须显式返回，静默丢弃正是 P0-2 的成因"
    assert set(REGISTRY) == {"summary", "uml_draft", "key_points", "code_blocks"}


def test_empty_output_schemas_fails_instead_of_reporting_success(video: Video):
    """产物集为空时解析注定零条目：必须 FAILED 并给出可执行的修法，不能 SUCCEEDED。"""
    from app.pipeline import parse_video

    broken = get_settings().model_copy(update={"output_schemas": " , "})
    assert broken.output_schema_list == []

    with Session(engine) as session:
        parsed = parse_video(session, session.get(Video, video.id), broken)
        items = session.exec(select(KnowledgeItem).where(KnowledgeItem.video_id == parsed.id)).all()

    assert items == [], "空产物集不该产出条目（这里是反证前提）"
    assert parsed.status == VideoStatus.FAILED, "零条目却 SUCCEEDED 是假成功"
    assert parsed.artifact_status == StageStatus.FAILED
    assert "产物集为空" in parsed.error
    assert "设置页" in parsed.error, "错误文本要能给用户一条可执行的路"


def test_schema_set_producing_zero_drafts_is_partial_not_success(video: Video):
    """产物集合法但一条没产出（如只勾代码块而画面通道关闭）：标 PARTIAL，零条目必须可见。"""
    from app.pipeline import bus, parse_video

    only_code = get_settings().model_copy(update={"output_schemas": "code_blocks"})
    q, _ = bus.subscribe(video.batch_id)
    try:
        with Session(engine) as session:
            parsed = parse_video(session, session.get(Video, video.id), only_code)
            items = session.exec(
                select(KnowledgeItem).where(KnowledgeItem.video_id == parsed.id)).all()
        _, history = bus.subscribe(video.batch_id)
    finally:
        bus.unsubscribe(q)

    assert items == []
    assert parsed.status == VideoStatus.PARTIAL
    assert parsed.artifact_status == StageStatus.PARTIAL
    # PARTIAL 的消息按现有 _set_stage 口径走事件流（只有 FAILED 才累加进 video.error）
    artifact_events = [e for e in history if e["stage"] == Stage.ARTIFACT.value]
    assert artifact_events[-1]["status"] == StageStatus.PARTIAL.value
    assert "未产出任何条目" in artifact_events[-1]["message"]


def test_saved_settings_with_unknown_schema_self_heals(tmp_path: Path, monkeypatch):
    """settings.json 被改坏（未知类型/重复/空）时启动读回要归一、回退并写回，不能留成空集。"""
    from app import main as app_main

    settings_path = Path(get_settings().media_root).parent / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({
        "schema_version": 2,
        "asr_engine": get_settings().asr_engine,
        "ocr_engine": get_settings().ocr_engine,
        "output_schemas": "summary,  summary ,已下线的产物",
    }, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(app_main._settings, "output_schemas", "")
    app_main._load_saved_settings()

    assert app_main._settings.output_schemas == "summary", "未知项被剔除、重复项被去重"
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["output_schemas"] == "summary", "归一结果要写回，否则下次启动再算一遍"
    settings_path.unlink(missing_ok=True)


def test_saved_settings_with_only_unknown_schemas_falls_back_to_default(tmp_path: Path, monkeypatch):
    """全是不认识的名字时回退默认四类——回退到空集等于把假成功又放回来。"""
    from app import main as app_main
    from app.config import DEFAULT_OUTPUT_SCHEMAS

    settings_path = Path(get_settings().media_root).parent / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({
        "schema_version": 2,
        "asr_engine": get_settings().asr_engine,
        "ocr_engine": get_settings().ocr_engine,
        "output_schemas": "已下线A,已下线B",
    }, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(app_main._settings, "output_schemas", "")
    app_main._load_saved_settings()

    assert app_main._settings.output_schemas == DEFAULT_OUTPUT_SCHEMAS
    settings_path.unlink(missing_ok=True)


# ── v0.17 P0-5：关键帧目录清理 + 帧间隔口径 ─────────────────────────────────


def _fake_frames(tmp_path: Path, ms_list: list[int]) -> list:
    """造一组「引擎刚抽出来的」关键帧（临时目录里的真实文件，_localize_frames 要 copy）。"""
    from app.engines.base import KeyFrame

    out = []
    for ms in ms_list:
        src = tmp_path / f"src_{ms}.jpg"
        src.write_bytes(b"\xff\xd8\xff\xe0stub")
        out.append(KeyFrame(ms=ms, path=str(src)))
    return out


def _frame_dir(video_id: int) -> Path:
    return Path(get_settings().media_root) / "frames" / str(video_id)


def test_rerun_prunes_stale_frame_files(video: Video, tmp_path: Path):
    """重跑换了一套关键帧：上一轮的帧文件必须被清掉，不能一直留在 /media 下当孤儿。"""
    from app.pipeline import _localize_frames

    first = _localize_frames(video.id, _fake_frames(tmp_path, [0, 30000, 60000]))
    assert len(list(_frame_dir(video.id).iterdir())) == 3

    second = _localize_frames(video.id, _fake_frames(tmp_path, [0, 90000]))
    kept = sorted(f.name for f in _frame_dir(video.id).iterdir())

    assert {f.ms for f in second} == {0, 90000}
    assert len(kept) == 2, f"上一轮 30000/60000 的帧应被清理，实际残留：{kept}"
    assert all(any(str(f.ms) in name for name in kept) for f in second)
    # 返回的路径必须仍指向真实存在的文件，清早了会让证据链断掉
    assert all(Path(f.path).exists() for f in second)
    assert first, "第一轮确实落过盘（反证前提）"


def test_frame_interval_env_drives_both_sampling_and_cache_key(video: Video, monkeypatch):
    """VMIND_FRAME_INTERVAL_S 必须同时影响「抽帧实参」和「缓存键」（v0.17 P0-5）。

    改前 pipeline 直接传常量，环境变量是死配置；而只把它塞进键、实参仍用常量的话，
    换间隔会拿别人的帧当自己的缓存命中，且不报任何错。
    """
    from app import cache
    from app import pipeline as pipeline_mod
    from app.engines.base import KeyFrame

    calls: list[float | None] = []

    def fake_sample(path, interval_s=None, **kwargs):
        calls.append(interval_s)
        src = Path(path).parent / "fake_frame.jpg"
        src.write_bytes(b"\xff\xd8\xff\xe0stub")
        return [KeyFrame(ms=0, path=str(src))]

    monkeypatch.setattr(pipeline_mod, "sample_frames", fake_sample)
    monkeypatch.setenv("VMIND_FRAME_INTERVAL_S", "5")

    with Session(engine) as session:
        frames = pipeline_mod._keyframes(session.get(Video, video.id))

    assert calls == [5.0], "实参必须来自同一份取值，而不是常量 30"
    assert frames and frames[0].ms == 0

    hit = cache.get(cache.key_of(video.path, "frames:5"))
    assert hit is not None, "缓存键要用 5 秒档位；用常量算键会让换档后命中别的缓存"
    assert cache.get(cache.key_of(video.path, "frames:30")) is None

    # 相同内容换档位：必须重抽，不能拿 5 秒档的结果当 30 秒档
    calls.clear()
    monkeypatch.setenv("VMIND_FRAME_INTERVAL_S", "30")
    with Session(engine) as session:
        pipeline_mod._keyframes(session.get(Video, video.id))
    assert calls == [30.0], "换档位必须重抽"


def test_invalid_frame_interval_falls_back_to_constant(monkeypatch):
    """非法/零/负数间隔回退默认值——配错了不能把抽帧变成无限循环或空跑。"""
    from app.engines.frames import FRAME_INTERVAL_S, effective_interval_s

    for raw in ("", "abc", "0", "-3"):
        monkeypatch.setenv("VMIND_FRAME_INTERVAL_S", raw)
        assert effective_interval_s() == FRAME_INTERVAL_S

    monkeypatch.setenv("VMIND_FRAME_INTERVAL_S", "7.5")
    assert effective_interval_s() == 7.5


def test_empty_frame_set_clears_previous_residue(video: Video, tmp_path: Path):
    """本轮一帧没抽到（换引擎/换参数失败）：上一轮残留也得清，否则界面上像仍有画面证据。"""
    from app.pipeline import _localize_frames

    _localize_frames(video.id, _fake_frames(tmp_path, [0, 30000]))
    assert _frame_dir(video.id).is_dir()

    assert _localize_frames(video.id, []) == []
    assert list(_frame_dir(video.id).iterdir()) == [], "无帧时不能留下上一轮的孤儿帧"


def test_prune_tolerates_missing_and_foreign_files(video: Video, tmp_path: Path):
    """目录不存在、或里面有非关键帧文件时清理不能抛——清理是纯优化。"""
    from app.pipeline import _localize_frames, _prune_frame_dir

    _prune_frame_dir(video.id, keep_ms=set())      # 目录不存在：不抛
    _localize_frames(video.id, _fake_frames(tmp_path, [0]))
    stray = _frame_dir(video.id) / "notes.txt"
    stray.write_text("不是我放的", encoding="utf-8")

    _prune_frame_dir(video.id, keep_ms={0})
    assert not stray.exists(), "非帧文件也一并清，目录约定只存关键帧"
    assert [f for f in _frame_dir(video.id).iterdir() if f.suffix == ".jpg"]
