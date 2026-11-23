"""v0.17 P0-3：缓存损坏兜底。

缓存的定位是**纯优化**——命中就省一次引擎/抽帧，读不出就必须当作未命中重跑。
改之前文件分支是裸 `json.loads(file.read_text())`：坏文件会让整条解析在①阶段直接
抛异常、被标成 TRANSCRIBE FAILED，用户看到「转写失败」而真正的原因是缓存坏了；
而且坏文件不会被清掉，这条视频此后每次都撞同一份坏缓存，只能人工去 data/cache 捞。
"""

from pathlib import Path

import pytest
from sqlmodel import Session, select

from app import cache
from app.config import get_settings
from app.db import engine, init_db
from app.enums import StageStatus, VideoStatus
from app.models import Segment, Video, VideoBatch
from app.pipeline import _asr_cache_ok, _frames_cache_ok, _keyframes, parse_video


@pytest.fixture(scope="module", autouse=True)
def _db():
    init_db()


def _cache_file(key: str) -> Path:
    return Path(get_settings().cache_root) / f"{key.replace(':', '_')}.json"


# ── 缓存层本身 ──────────────────────────────────────────────────────────────


def test_corrupt_json_is_a_miss_and_gets_removed():
    """坏 JSON 不许抛异常，要当未命中并删掉坏文件（否则每次重跑都撞同一份坏缓存）。"""
    key = "vmind:test:corrupt"
    file = _cache_file(key)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('{"duration_ms": 1000, "segments": [', encoding="utf-8")

    assert cache.get(key) is None
    assert not file.exists(), "坏缓存要清掉，不然这条视频永久读不出"


def test_unreadable_bytes_are_a_miss(monkeypatch):
    """编码坏（非 UTF-8 字节）同样只能是未命中，不能把 UnicodeDecodeError 抛给调用方。"""
    key = "vmind:test:badbytes"
    file = _cache_file(key)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b"\xff\xfe\x00not json at all")

    assert cache.get(key) is None
    assert not file.exists()


def test_valid_json_with_wrong_shape_is_a_miss():
    """合法 JSON 但结构不对（旧版本缓存）也得当未命中——不然会在 KeyFrame(**) 里炸。"""
    key = "vmind:test:oldshape"
    cache.put(key, {"duration_ms": 1000})       # 缺 segments
    assert cache.get(key, validate=_asr_cache_ok) is None
    assert not _cache_file(key).exists()

    cache.put(key, ["不是帧列表"])
    assert cache.get(key, validate=_frames_cache_ok) is None


def test_write_failure_only_warns(tmp_path: Path, monkeypatch):
    """磁盘满/权限不足时写缓存失败只能告警，绝不能让解析失败。"""
    bad_root = tmp_path / "not_a_dir"
    bad_root.write_text("我是文件，不是目录", encoding="utf-8")
    monkeypatch.setattr(cache._settings, "cache_root", str(bad_root))

    cache.put("vmind:test:writefail", {"duration_ms": 1})   # 不抛即通过


def test_discard_tolerates_missing_entry():
    cache.discard("vmind:test:never-existed")   # 不抛即通过


# ── 接进主链路：坏缓存不能让用户看到「转写失败」 ────────────────────────────


@pytest.fixture()
def video(tmp_path: Path) -> Video:
    src = tmp_path / "vue3_lecture.mp4"
    src.write_bytes(b"\x00")
    with Session(engine) as session:
        batch = VideoBatch(name="缓存兜底批次", video_count=1)
        session.add(batch)
        session.commit()
        session.refresh(batch)
        video = Video(batch_id=batch.id, path=str(src))
        session.add(video)
        session.commit()
        session.refresh(video)
        return video


def test_corrupt_asr_cache_does_not_fail_the_transcribe_stage(video: Video):
    """核心回归：缓存坏了 → 重跑一次转写，阶段必须照常 DONE，而不是 TRANSCRIBE FAILED。"""
    from app.engines.base import build_asr
    from app.pipeline import _asr_cache_name

    key = cache.key_of(video.path, _asr_cache_name(build_asr(get_settings().asr_engine)))
    file = _cache_file(key)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("{ 半截的 JSON", encoding="utf-8")

    with Session(engine) as session:
        parsed = parse_video(session, session.get(Video, video.id))
        segments = session.exec(select(Segment).where(Segment.video_id == parsed.id)).all()

    assert parsed.transcribe_status == StageStatus.DONE, "缓存坏了不该被记成转写失败"
    assert parsed.status == VideoStatus.SUCCEEDED
    assert segments, "重跑必须真正产出一份转写"
    assert cache.get(key) is not None, "重跑完应写回一份好缓存"


def test_corrupt_frames_cache_falls_back_to_re_sampling(video: Video, monkeypatch):
    """帧缓存坏了 → 重抽一次帧，不能因为 KeyFrame(**) 取值失败把①阶段拖垮。"""
    import app.pipeline as pipeline_mod
    from app.engines.frames import FRAME_INTERVAL_S

    cache_key = cache.key_of(video.path, f"frames:{FRAME_INTERVAL_S:g}")
    file = _cache_file(cache_key)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('{"不是": "帧列表"}', encoding="utf-8")

    calls: list[str] = []
    real_sample = pipeline_mod.sample_frames

    def spy_sample(path, interval_s=None, **kwargs):
        calls.append(path)
        return real_sample(path, interval_s, **kwargs)

    monkeypatch.setattr(pipeline_mod, "sample_frames", spy_sample)

    with Session(engine) as session:
        frames = _keyframes(session.get(Video, video.id))

    assert calls == [video.path], "坏缓存必须导致重抽，而不是直接当空帧返回"
    assert isinstance(frames, list), "返回值形状不能变，抽样失败也该是空列表而不是异常"
