"""解析结果缓存 —— 对应风险 #6「单台 4070 排队」：同一条视频命中缓存则不重跑。"""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import get_settings

_settings = get_settings()
_redis = None

if _settings.redis_url:
    try:
        import redis

        _redis = redis.Redis.from_url(_settings.redis_url, decode_responses=True, socket_timeout=1)
    except Exception:
        _redis = None


def key_of(path: str, engine_name: str) -> str:
    digest = hashlib.sha256(f"{Path(path).name}:{Path(path).stat().st_size}:{engine_name}".encode()).hexdigest()
    return f"vmind:{engine_name}:{digest[:24]}"


def get(key: str) -> Any | None:
    if _redis is not None:
        try:
            raw = _redis.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            pass
    file = Path(_settings.cache_root) / f"{key.replace(':', '_')}.json"
    if file.exists():
        return json.loads(file.read_text(encoding="utf-8"))
    return None


def put(key: str, value: Any) -> None:
    if _redis is not None:
        try:
            _redis.setex(key, 86400, json.dumps(value, ensure_ascii=False))
            return
        except Exception:
            pass
    root = Path(_settings.cache_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{key.replace(':', '_')}.json").write_text(
        json.dumps(value, ensure_ascii=False), encoding="utf-8"
    )
