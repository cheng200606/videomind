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


_CHUNK_SIZE = 1024 * 1024


def _file_sha256(source: Path) -> str:
    """流式算内容摘要：分块读，整条视频也不会一次进内存。"""
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def key_of(path: str, engine_name: str) -> str:
    """缓存键内容寻址：同名同大小但内容不同的文件不再共用旧解析结果。"""
    source = Path(path)
    try:
        identity = f"sha256:{_file_sha256(source)}"
    except OSError:
        # 文件已删/被占用：退回旧的 name:size 口径，不让缓存环节打断解析
        try:
            identity = f"stat:{source.name}:{source.stat().st_size}"
        except OSError:
            identity = f"stat:{source.name}:unreadable"
    digest = hashlib.sha256(f"{identity}:{engine_name}".encode()).hexdigest()
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
