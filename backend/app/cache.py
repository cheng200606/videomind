"""解析结果缓存 —— 对应风险 #6「单台 4070 排队」：同一条视频命中缓存则不重跑。

缓存是**纯优化**，任何环节出问题都不能打断解析（v0.17 P0-3）：读坏了当作未命中并
清掉坏文件（否则该视频此后每次都撞同一份坏缓存，只能等人工删），写失败只告警。
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.config import get_settings

_log = logging.getLogger("videomind.cache")

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


def _file_path(key: str) -> Path:
    return Path(_settings.cache_root) / f"{key.replace(':', '_')}.json"


def discard(key: str) -> None:
    """丢掉一条缓存（读到坏内容时调）。删不掉也不影响解析，只记日志。"""
    if _redis is not None:
        try:
            _redis.delete(key)
        except Exception as exc:
            _log.warning("缓存条目删除失败（redis）：%s", exc)
    try:
        _file_path(key).unlink(missing_ok=True)
    except OSError as exc:
        _log.warning("缓存文件删除失败（%s）：%s", _file_path(key).name, exc)


def get(key: str, validate=None) -> Any | None:
    """读缓存；**任何损坏都按未命中处理，绝不抛异常打断解析**。

    validate：可选结构校验函数，返回 False 视为损坏。光靠 json.loads 成功不够——
    程序升级后旧缓存的结构可能已变（少了字段/换了类型），那种「合法 JSON 但用不了」
    的条目会让调用方在取值时炸，用户看到的却是阶段失败而不是缓存问题。

    损坏条目会顺手删掉：否则该视频此后每次都撞同一份坏缓存，只能等人工去 data/cache 里捞。
    """
    if _redis is not None:
        try:
            raw = _redis.get(key)
            if raw:
                value = json.loads(raw)
                if validate is None or validate(value):
                    return value
                _log.warning("缓存内容结构不符，已丢弃：%s", key)
                discard(key)
        except Exception as exc:
            # 连不上/读不出：退回文件缓存，再不行就当未命中
            _log.warning("缓存读取失败（redis），按未命中处理：%s", exc)

    file = _file_path(key)
    if not file.exists():
        return None
    try:
        value = json.loads(file.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        # JSON 坏 / 编码坏 / 半截文件：删掉重跑，不让它把整条解析按阶段失败处理
        _log.warning("缓存文件损坏，已删除并重跑解析：%s（%s）", file.name, exc)
        discard(key)
        return None
    if validate is not None and not validate(value):
        _log.warning("缓存内容结构不符（可能来自旧版本），已丢弃：%s", file.name)
        discard(key)
        return None
    return value


def put(key: str, value: Any) -> None:
    """写缓存；**写失败只告警**，不能因为磁盘满/权限问题让解析失败。"""
    if _redis is not None:
        try:
            _redis.setex(key, 86400, json.dumps(value, ensure_ascii=False))
            return
        except Exception as exc:
            _log.warning("缓存写入失败（redis），改用文件缓存：%s", exc)
    file = _file_path(key)
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        # 先写临时文件再 replace：中途崩溃不留半截 JSON（那种文件下次必被判定损坏）
        tmp = file.with_name(f"{file.name}.tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        tmp.replace(file)
    except OSError as exc:
        _log.warning("缓存写入失败（%s）：%s", file.name, exc)
