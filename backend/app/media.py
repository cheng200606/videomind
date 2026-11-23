"""媒体文件的展示名与 /media URL：落盘名带批次前缀，UI 只应看到原始文件名。"""

from pathlib import Path
from urllib.parse import quote


def stored_name(path: str) -> str:
    return Path(path).name


def display_name(path: str, batch_id: int) -> str:
    name = stored_name(path)
    prefix = f"{batch_id}_"
    return name[len(prefix):] if name.startswith(prefix) else name


def media_url(path: str) -> str:
    return f"/media/{quote(stored_name(path))}"
