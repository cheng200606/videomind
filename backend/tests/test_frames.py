"""独立关键帧抽样单测：用 av 现场编码合成视频验证采样与相似帧去重。

不依赖任何素材文件；av 属可选重依赖，未安装时整文件跳过。
"""

from pathlib import Path

import pytest

av = pytest.importorskip("av")
np = pytest.importorskip("numpy")

from app.engines.frames import sample_frames   # noqa: E402


def _make_video(path: Path, colors: list[tuple[int, int, int]], fps: int = 1) -> None:
    """合成 1 fps 的小视频：每秒一帧纯色画面，颜色序列由调用方控制。"""
    container = av.open(str(path), mode="w", format="mp4")
    stream = container.add_stream("libx264", rate=fps)
    stream.width, stream.height, stream.pix_fmt = 64, 64, "yuv420p"
    stream.options = {"preset": "ultrafast"}
    for color in colors:
        arr = np.full((64, 64, 3), color, dtype=np.uint8)
        for packet in stream.encode(av.VideoFrame.from_ndarray(arr, format="rgb24")):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def test_sample_frames_picks_changing_scenes(tmp_path: Path):
    """每秒画面都变：interval=1s 应采到全部 3 帧，时间戳单调。"""
    video = tmp_path / "scene.mp4"
    _make_video(video, [(255, 0, 0), (0, 255, 0), (0, 0, 255)])
    frames = sample_frames(str(video), interval_s=1.0)
    assert len(frames) == 3
    assert [f.ms for f in frames] == [0, 1000, 2000]
    assert all(Path(f.path).exists() for f in frames)


def test_sample_frames_dedupes_identical_slides(tmp_path: Path):
    """满屏静态课件连续采样几乎相同：同色画面只保留第一帧。"""
    video = tmp_path / "static.mp4"
    _make_video(video, [(30, 30, 30)] * 4)
    frames = sample_frames(str(video), interval_s=1.0)
    assert len(frames) == 1, "相邻同画面应被 16x16 均值差去重"


def test_sample_frames_degrades_on_bad_file(tmp_path: Path):
    """坏文件/无视频流只返回空列表，绝不能抛异常拖垮解析。"""
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"not a video at all")
    assert sample_frames(str(bad), interval_s=1.0) == []
    audio_only = tmp_path / "audioonly.mp4"
    _make_video(audio_only, [(1, 2, 3)])   # 正常文件保底可跑
    assert sample_frames(str(audio_only), interval_s=1.0)
