"""引擎接缝 —— 类图图 5 里的 `AsrEngine` / `OcrEngine` 抽象在此，实现类在 asr.py / ocr.py。"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class TranscriptSegment:
    index: int
    start_ms: int
    end_ms: int
    text: str
    confidence: float = 0.0


@dataclass
class KeyFrame:
    ms: int
    path: str


@dataclass
class AsrResult:
    duration_ms: int = 0
    segments: list[TranscriptSegment] = field(default_factory=list)
    frames: list[KeyFrame] = field(default_factory=list)   # yueying 抽帧顺带产出


@dataclass
class FrameText:
    ms: int
    text: str
    confidence: float = 0.0
    box: Sequence[float] | None = None


class AsrEngine(Protocol):
    name: str

    def transcribe(self, video_path: str) -> AsrResult: ...


class OcrEngine(Protocol):
    name: str

    def recognize(self, frames: Sequence[KeyFrame]) -> list[FrameText]: ...


_ASR: dict[str, type] = {}
_OCR: dict[str, type] = {}


def register_asr(name: str):
    def wrap(cls: type) -> type:
        _ASR[name] = cls
        return cls
    return wrap


def register_ocr(name: str):
    def wrap(cls: type) -> type:
        _OCR[name] = cls
        return cls
    return wrap


def available_asr() -> list[str]:
    return sorted(_ASR)


def available_ocr() -> list[str]:
    return sorted(_OCR)


def build_asr(name: str) -> AsrEngine:
    if name not in _ASR:
        raise KeyError(f"未知 ASR 引擎 {name!r}，可选：{available_asr()}")
    return _ASR[name]()


def build_ocr(name: str) -> OcrEngine | None:
    if name in ("", "none"):
        return None
    if name not in _OCR:
        raise KeyError(f"未知 OCR 引擎 {name!r}，可选：{available_ocr()}")
    return _OCR[name]()
