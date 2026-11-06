"""独立关键帧抽样：av 解码视频流，按固定间隔取帧。

yueying 的抽帧随其缺席而消失（桌面版只带 Whisper，纯音频通道），画面通道要在此也能用，
抽帧必须不依赖任何 ASR 引擎。相邻相似帧用 16x16 灰度缩略的均值差丢弃——numpy 手写，
不引入 imagehash+scipy（桌面安装包要为它们多付约 120MB）。
"""

import os
import tempfile
from pathlib import Path

from app.engines.base import KeyFrame

# 采样间隔（秒）：30s 对讲座类内容足够密，1h 视频约 120 帧，RapidOCR 2 线程约 1-2 分钟
FRAME_INTERVAL_S = 30.0
_MAX_FRAMES = 400          # 兜底上限：异常超长视频不至于拖死解析
_SIMILAR_THRESHOLD = 6.0   # 16x16 灰度均值差低于该值视为同页课件，丢弃


def _interval_from_env() -> float:
    raw = os.environ.get("VMIND_FRAME_INTERVAL_S", "")
    try:
        value = float(raw)
    except ValueError:
        return FRAME_INTERVAL_S
    return value if value > 0 else FRAME_INTERVAL_S


def sample_frames(video_path: str, interval_s: float | None = None,
                  max_frames: int = _MAX_FRAMES) -> list[KeyFrame]:
    """按 interval 抽帧；相邻缩略图均值差过小的帧丢弃（满屏课件连续采样几乎相同）。

    任何失败（无视频流、编码不支持、缺 PIL）都返回已抽到的部分或空列表——
    抽帧失败只应让画面通道降级为 SKIPPED，不能拖垮整条解析。
    """
    try:
        import av
        import numpy as np
    except ImportError:
        return []

    interval = interval_s or _interval_from_env()
    out: list[KeyFrame] = []
    try:
        tmp = Path(tempfile.mkdtemp(prefix="vmind_frames_"))
        container = av.open(video_path)
    except Exception:
        return out

    next_ts = 0.0
    last_thumb: np.ndarray | None = None
    try:
        with container:
            if not container.streams.video:
                return out
            duration_s = (container.duration or 0) / 1_000_000
            # 异常长的视频自动放粗间隔，保证帧数有上限
            if duration_s > max_frames * interval:
                interval = duration_s / max_frames
            for frame in container.decode(video=0):
                ts = frame.time
                if ts is None or ts + 1e-6 < next_ts:
                    continue
                thumb = frame.reformat(width=16, height=16, format="gray").to_ndarray()
                if last_thumb is not None and _abs_diff(thumb, last_thumb) < _SIMILAR_THRESHOLD:
                    next_ts = ts + interval
                    continue
                path = tmp / f"frame_{int(ts * 1000)}.jpg"
                try:
                    frame.to_image().save(path)
                except Exception:   # 缺 PIL 等存图失败：画面通道降级，不影响音频通道
                    return out
                out.append(KeyFrame(ms=int(ts * 1000), path=str(path)))
                last_thumb = thumb.astype("float32")
                next_ts = ts + interval
                if len(out) >= max_frames:
                    break
    except Exception:
        return out
    return out


def _abs_diff(a: "np.ndarray", b: "np.ndarray") -> float:
    import numpy as np

    return float(np.abs(a.astype("float32") - b).mean())
