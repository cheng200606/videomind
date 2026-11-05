"""引擎实现与注册入口。导入本模块即完成注册。"""

from app.engines import asr, ocr  # noqa: F401

__all__ = ["asr", "ocr"]
