"""设置页：自定义大模型配置（DeepSeek / 自定义 OpenAI 兼容接口）。

Key 只写本机 data/model_settings.json；GET/PUT 响应均不返回明文。
"""

import re
import time
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.llm import test_connection
from app.model_config import PROVIDERS, ModelConfig, active_model_config, save_model_config

router = APIRouter(prefix="/api", tags=["settings"])


class ModelSettingsIn(BaseModel):
    provider: str = "deepseek"
    base_url: str
    model: str
    api_key: str | None = None
    clear_api_key: bool = False


def _public(cfg: ModelConfig) -> dict:
    return {
        "provider": cfg.provider,
        "base_url": cfg.base_url,
        "model": cfg.model,
        "has_key": bool(cfg.api_key),
        "source": cfg.source,
    }


def _clean_url(raw: str) -> str:
    url = raw.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(422, "Base URL 必须是完整的 http(s) 地址")
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and host not in ("localhost", "127.0.0.1", "::1"):
        raise HTTPException(422, "远程模型地址必须使用 HTTPS；仅本机调试允许 HTTP")
    return url.rstrip("/")


def _safe_error(exc: Exception, key: str) -> str:
    text = str(exc)
    if key:
        text = text.replace(key, "***")
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer ***", text)
    return text[:300]


@router.get("/settings/model")
def get_model_settings():
    return _public(active_model_config())


@router.put("/settings/model")
def set_model_settings(body: ModelSettingsIn):
    provider = body.provider.strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(422, f"未知模型提供方，可选 {list(PROVIDERS)}")
    base_url = _clean_url(body.base_url)
    model = body.model.strip()
    if not model:
        raise HTTPException(422, "模型名不能为空")
    if len(model) > 200:
        raise HTTPException(422, "模型名过长（不超过 200 字）")

    current = active_model_config()
    api_key = current.api_key
    if body.clear_api_key:
        api_key = ""
    elif body.api_key is not None and body.api_key.strip():
        api_key = body.api_key.strip()
    if len(api_key) > 512:
        raise HTTPException(422, "API Key 过长（不超过 512 字）")

    return _public(save_model_config(provider, base_url, model, api_key))


@router.post("/settings/model/test")
def test_model_settings():
    cfg = active_model_config()
    if not cfg.api_key:
        raise HTTPException(422, "尚未配置 API Key")
    start = time.perf_counter()
    try:
        text, latency = test_connection(cfg)
        return {
            "ok": True,
            "latency_ms": latency,
            "model": cfg.model,
            "message": (text or "OK")[:80],
        }
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "model": cfg.model,
            "error": _safe_error(exc, cfg.api_key),
        }
