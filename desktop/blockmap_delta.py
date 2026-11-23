"""对比两个 electron-builder blockmap v2（gzip JSON），估算 electron-updater 差分下载量。

用法：
  backend/.venv/Scripts/python desktop/blockmap_delta.py <old.exe.blockmap> <new.exe.blockmap> <new.exe字节数>

按 index 对齐逐块比 checksum（electron-updater 的对齐方式）。
2026-11-07 实测结论（docs/桌面版发布方案.md §四）：NSIS 安装包内嵌构建时间戳，
同版本两次构建即 99% 块不同——差分对独立构建结构性失效，此脚本留作复核工具。
"""

import gzip
import json
import sys


def load(path: str) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)["files"][0]["checksums"]


old, new = load(sys.argv[1]), load(sys.argv[2])
size = int(sys.argv[3])
block = round(size / len(new))
changed = sum(1 for i, c in enumerate(new) if i >= len(old) or old[i] != c)
print(f"blocks: old={len(old)} new={len(new)}  block_size~{block / 1024:.0f}KB")
print(f"changed: {changed} / {len(new)}")
print(f"delta download ~ {changed * block / 1024 / 1024:.0f} MB / {size / 1024 / 1024:.0f} MB ({changed * 100 // len(new)}%)")
