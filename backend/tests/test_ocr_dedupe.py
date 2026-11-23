"""OCR 帧去重：与抽帧阶段同口径，且不依赖桌面发行版已排除的 imagehash。

回归背景：旧 dedupe_frames 在 ImportError 时静默返回全部帧，桌面包排除
imagehash/scipy 后去重等于没做，且没有任何可见提示（v0.14 修复）。
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")  # noqa: E402
pytest.importorskip("PIL")  # noqa: E402
from PIL import Image  # noqa: E402

from app.engines.base import KeyFrame  # noqa: E402
from app.engines.frames import SIMILAR_THRESHOLD, abs_diff, file_thumbnail  # noqa: E402
from app.engines.ocr import dedupe_frames  # noqa: E402


def _frame(tmp_path: Path, name: str, color: tuple[int, int, int], ms: int) -> KeyFrame:
    path = tmp_path / f"{name}.png"
    Image.new("RGB", (64, 64), color).save(path)
    return KeyFrame(ms=ms, path=str(path))


def test_dedupe_frames_works_without_imagehash(tmp_path: Path, monkeypatch):
    """模拟桌面发行版（imagehash 被排除）：去重仍生效，不再静默跳过。"""
    # sys.modules[name] = None 会让 import 抛 ModuleNotFoundError
    monkeypatch.setitem(sys.modules, "imagehash", None)
    frames = [
        _frame(tmp_path, "a", (30, 30, 30), 0),
        _frame(tmp_path, "b", (30, 30, 30), 1000),   # 同页课件，应被丢弃
        _frame(tmp_path, "c", (220, 220, 220), 2000),
    ]
    kept = dedupe_frames(frames)
    assert [f.ms for f in kept] == [0, 2000], "重复课件帧应被丢弃，不同画面应保留"


def test_dedupe_uses_same_signature_as_frame_sampling(tmp_path: Path):
    """去重口径与抽帧阶段一致：同图差为 0，异图差远大于阈值。"""
    same = file_thumbnail(_frame(tmp_path, "s1", (10, 10, 10), 0).path)
    same2 = file_thumbnail(_frame(tmp_path, "s2", (10, 10, 10), 1).path)
    other = file_thumbnail(_frame(tmp_path, "o", (240, 240, 240), 2).path)
    assert same is not None and same2 is not None and other is not None
    assert abs_diff(same, same2) < SIMILAR_THRESHOLD
    assert abs_diff(same, other) >= SIMILAR_THRESHOLD


def test_dedupe_keeps_unreadable_frames_and_warns(tmp_path: Path, caplog):
    """读图失败只保留该帧并留可见日志，绝不因去重优化丢画面。"""
    good = _frame(tmp_path, "good", (30, 30, 30), 0)
    bad_path = tmp_path / "broken.png"
    bad_path.write_bytes(b"not an image")
    bad = KeyFrame(ms=1000, path=str(bad_path))
    with caplog.at_level("WARNING"):
        kept = dedupe_frames([good, bad])
    assert [f.ms for f in kept] == [0, 1000]
    assert "关键帧去重部分不可用" in caplog.text
