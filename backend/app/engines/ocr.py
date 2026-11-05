"""`OcrEngine` 的三个实现 + 关键帧去重。画面通道（阶段 ②）在此。"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.engines.base import FrameText, KeyFrame, register_ocr

_settings = get_settings()


def dedupe_frames(frames: Sequence[KeyFrame], threshold: int = 8) -> list[KeyFrame]:
    """满屏代码的课件连续帧几乎相同，去重后才送 OCR / LLM——直接省 token 与显存排队时间。"""
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return list(frames)

    kept: list[KeyFrame] = []
    seen: list[Any] = []
    for frame in frames:
        try:
            digest = imagehash.phash(Image.open(frame.path))
        except Exception:
            kept.append(frame)
            continue
        if any(abs(digest - prev) <= threshold for prev in seen):
            continue
        seen.append(digest)
        kept.append(frame)
    return kept or list(frames)


def _unwrap(result) -> tuple[list[str], list[float], list]:
    """把 RapidOCR 返回值归一成 (texts, scores, boxes)。

    v3.x 返回带 txts/scores/boxes 的结果对象；1.x（rapidocr-onnxruntime）返回
    (每行 [box, text, score], 耗时) 元组。本项目锁 3.10.0，装好后打印一次
    type(result) 就能确认走哪条分支，另一条只在换版本时兜住。
    """
    if hasattr(result, "txts"):
        return list(result.txts or []), list(result.scores or []), list(result.boxes or [])
    rows = result[0] if isinstance(result, tuple) else result
    rows = list(rows or [])
    if rows and isinstance(rows[0], dict):
        return ([r.get("txt", "") for r in rows], [float(r.get("score", 0.0)) for r in rows],
                [r.get("box", []) for r in rows])
    return ([r[1] for r in rows], [float(r[2]) for r in rows], [r[0] for r in rows])


@register_ocr("rapid")
class RapidOcr:
    """★主 OCR：PaddleOCR 模型转 ONNX，不拖 paddle 框架，CPU 可跑。"""

    name = "rapid"
    _engine = None

    def _load(self):
        if RapidOcr._engine is None:
            from rapidocr import RapidOCR

            RapidOcr._engine = RapidOCR()
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
