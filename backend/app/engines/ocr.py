"""`OcrEngine` 的三个实现 + 关键帧去重。画面通道（阶段 ②）在此。"""

import importlib.util
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.engines.base import FrameText, KeyFrame, register_ocr
from app.engines.frames import SIMILAR_THRESHOLD, abs_diff, file_thumbnail

logger = logging.getLogger(__name__)
_settings = get_settings()


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def dedupe_frames(frames: Sequence[KeyFrame],
                  threshold: float = SIMILAR_THRESHOLD) -> list[KeyFrame]:
    """满屏代码的课件连续帧几乎相同，去重后才送 OCR / LLM——省 token 与推理时间。

    与抽帧阶段（`app/engines/frames.py`）共用 16x16 灰度均值差口径，只依赖 Pillow +
    numpy（OCR 运行时自带、桌面包内亦有）。旧实现用 imagehash.phash，而桌面发行版
    明确排除 imagehash/scipy，`ImportError` 分支会静默跳过去重——降级既不可见，也让
    正式发布物与源码行为不一致。现在读图失败只保留该帧并记 warning，不丢画面。
    """
    kept: list[KeyFrame] = []
    seen: list[Any] = []
    unavailable = False
    for frame in frames:
        thumb = file_thumbnail(frame.path)
        if thumb is None:
            unavailable = True
            kept.append(frame)
            continue
        if any(abs_diff(thumb, prev) < threshold for prev in seen):
            continue
        seen.append(thumb)
        kept.append(frame)
    if unavailable:
        logger.warning("关键帧去重部分不可用（无法读取帧缩略图），相关帧已原样保留送 OCR")
    return kept or list(frames)


def _unwrap(result) -> tuple[list[str], list[float], list]:
    """把 RapidOCR 返回值归一成 (texts, scores, boxes)。

    v3.x 返回带 txts/scores/boxes 的结果对象；1.x（rapidocr-onnxruntime）返回
    (每行 [box, text, score], 耗时) 元组。numpy 数组不能直接做布尔判断，
    统一先 list() 再归一，避免 "truth value of an array is ambiguous"。
    """
    def _as_list(value):
        return [] if value is None else list(value)

    if hasattr(result, "txts"):
        return (_as_list(getattr(result, "txts", None)),
                _as_list(getattr(result, "scores", None)),
                _as_list(getattr(result, "boxes", None)))
    rows = result[0] if isinstance(result, tuple) else result
    rows = _as_list(rows)
    if rows and isinstance(rows[0], dict):
        return ([r.get("txt", "") for r in rows],
                [float(r.get("score", 0.0)) for r in rows],
                [r.get("box", []) for r in rows])
    return ([r[1] for r in rows], [float(r[2]) for r in rows], [r[0] for r in rows])


@register_ocr("rapid")
class RapidOcr:
    """★主 OCR：PaddleOCR 模型转 ONNX，不拖 paddle 框架，CPU 可跑。"""

    name = "rapid"
    _engine = None

    @staticmethod
    def is_available() -> bool:
        return _has_module("rapidocr")

    def _load(self):
        if RapidOcr._engine is None:
            from rapidocr import RapidOCR

            # 默认 ONNX Runtime 按 CPU 核数建线程池，实测常驻约 1.6 GB；
            # 长视频里还要同时跑 ASR 子进程，限制到 2 线程可降到约 0.9 GB
            RapidOcr._engine = RapidOCR(params={
                "EngineConfig.onnxruntime.intra_op_num_threads": 2,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            })
        return RapidOcr._engine

    def recognize(self, frames: Sequence[KeyFrame]) -> list[FrameText]:
        out: list[FrameText] = []
        for frame in dedupe_frames(frames):
            texts, scores, boxes = _unwrap(self._load()(frame.path))
            for text, score, box in zip(texts, scores, boxes):
                out.append(FrameText(ms=frame.ms, text=text, confidence=float(score),
                                     box=list(box) if box is not None else None))
        return out


@register_ocr("paddle")
class PaddleOcr:
    """与 RapidOcr 并列的第二个实现——`OcrEngine` 的「可插拔」由此有码可证，不是画出来的。"""

    name = "paddle"
    _engine = None

    @staticmethod
    def is_available() -> bool:
        return _has_module("paddleocr")

    def _load(self):
        if PaddleOcr._engine is None:
            from paddleocr import PaddleOCR

            PaddleOcr._engine = PaddleOCR(use_textline_orientation=True, use_doc_orientation_classify=False)
        return PaddleOcr._engine

    def recognize(self, frames: Sequence[KeyFrame]) -> list[FrameText]:
        out: list[FrameText] = []
        for frame in dedupe_frames(frames):
            for page in self._load().predict(frame.path):
                texts = page.get("rec_texts", []) if hasattr(page, "get") else getattr(page, "rec_texts", [])
                scores = page.get("rec_scores", []) if hasattr(page, "get") else getattr(page, "rec_scores", [])
                for text, score in zip(texts, scores):
                    out.append(FrameText(ms=frame.ms, text=text, confidence=float(score)))
        return out


@register_ocr("vision")
class VisionModelOcr:
    """视觉大模型通道：直接问「这一帧上的代码/文字是什么」，对糊帧更稳，但花钱且慢。

    走 OpenAI 兼容协议，端点与模型由环境变量指定（DeepSeek 文本模型不带视觉）。
    """

    name = "vision"

    @staticmethod
    def is_available() -> bool:
        # 只有显式配置了视觉端点/Key 才可选；DeepSeek 文本 Key 不能当视觉模型用
        return bool(os.environ.get("VISION_API_KEY"))

    def recognize(self, frames: Sequence[KeyFrame]) -> list[FrameText]:
        import base64
        import os

        import httpx

        url = f"{os.environ.get('VISION_BASE_URL', _settings.deepseek_base_url).rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {os.environ.get('VISION_API_KEY') or _settings.deepseek_api_key}"}
        model = os.environ.get("VISION_MODEL", "qwen-vl-plus")

        out: list[FrameText] = []
        for frame in dedupe_frames(frames):
            data = base64.b64encode(Path(frame.path).read_bytes()).decode()
            resp = httpx.post(
                url, headers=headers, timeout=180,
                json={
                    "model": model, "max_tokens": 800,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "逐行输出这一帧上出现的代码或文字，保持原缩进，不要解释。"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
                        ],
                    }],
                },
            )
            resp.raise_for_status()
            text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
            if text:
                out.append(FrameText(ms=frame.ms, text=text, confidence=0.6))
        return out
