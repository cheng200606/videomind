"""运行时大模型配置：设置页写入本机 data 目录，接口不回传 Key。

优先级：本机 model_settings.json > 环境变量 > 默认值。
文件位于 media_root 的父目录（与 settings.json 同级），随 backend/data/ 一起 gitignore。
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
PROVIDERS = ("deepseek", "custom")

_active: "ModelConfig | None" = None


@dataclass
class ModelConfig:
    provider: str = "deepseek"
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str = ""
    source: str = "default"   # saved / env / default


def _config_path() -> Path:
    return Path(get_settings().media_root).parent / "model_settings.json"


def _from_env() -> ModelConfig:
    settings = get_settings()
    key = os.environ.get("DEEPSEEK_API_KEY") or settings.deepseek_api_key
    return ModelConfig(
        provider="deepseek",
        base_url=os.environ.get("DEEPSEEK_BASE_URL") or settings.deepseek_base_url,
        model=os.environ.get("DEEPSEEK_MODEL") or settings.deepseek_model,
        api_key=key,
        source="env" if key else "default",
    )


def load_model_config() -> ModelConfig:
    path = _config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _from_env()
        provider = str(data.get("provider") or "deepseek")
        return ModelConfig(
            provider=provider if provider in PROVIDERS else "deepseek",
            base_url=str(data.get("base_url") or DEFAULT_BASE_URL),
            model=str(data.get("model") or DEFAULT_MODEL),
            api_key=str(data.get("api_key") or ""),
            source="saved",
        )
    return _from_env()


def active_model_config() -> ModelConfig:
    global _active
    if _active is None:
        _active = load_model_config()
    return _active


def save_model_config(provider: str, base_url: str, model: str, api_key: str) -> ModelConfig:
    global _active
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    _active = ModelConfig(provider=provider, base_url=base_url, model=model,
                          api_key=api_key, source="saved")
    return _active


def reset_model_config_cache() -> None:
    """测试与启动时用：让下一次 active_model_config() 重新读文件。"""
    global _active
    _active = None
