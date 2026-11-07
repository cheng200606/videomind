"""生成文件级增量更新包：对比两个 win-unpacked 目录，只打包变更文件 + manifest。

用法（版本号已升、双版本产物齐备时）：
  backend/.venv/Scripts/python desktop/make_update_zip.py \
      --from release/win-unpacked-0.12.0 \
      --to   release/win-unpacked \
      --version 0.12.1 --base 0.12.0 \
      --out  release/VideoMind-update-0.12.1.zip

产物：
  - update zip：仅含相对路径有增改的文件（app.asar、resources/backend/VideoMindBackend.exe 等）
  - manifest json：files[{path,sha256,size,action}] / deleted[] / base_version / 整包 sha256
    （应用内更新器按 manifest 逐文件校验后替换；Electron 壳与引擎运行时不变则不在包内）

背景（2026-11-07 实测，docs/桌面版发布方案.md §四）：electron-builder NSIS 内嵌构建时间
戳，同版本两次构建即 99% 块不同——electron-updater 差分结构性失效，全量 259MB/次；
本脚本是「增量更新包」路线（阶段 2）的生成端，应用端替换逻辑见方案文档。
"""

import argparse
import gzip
import hashlib
import json
import zipfile
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(root: Path) -> dict[str, Path]:
    return {p.relative_to(root).as_posix(): p
            for p in root.rglob("*") if p.is_file()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="old", type=Path, required=True, help="上一版 win-unpacked")
    ap.add_argument("--to", dest="new", type=Path, required=True, help="当前版 win-unpacked")
    ap.add_argument("--version", required=True)
    ap.add_argument("--base", required=True, help="增量基于的上一版本号")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    old_files, new_files = _walk(args.old), _walk(args.new)
    entries, deleted = [], []
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel, path in sorted(new_files.items()):
            old_path = old_files.get(rel)
            if old_path is not None and _sha256(old_path) == _sha256(path):
                continue
            action = "replace" if old_path is not None else "add"
            sha = _sha256(path)
            zf.write(path, rel)
            entries.append({"path": rel, "sha256": sha,
                            "size": path.stat().st_size, "action": action})
        deleted = sorted(set(old_files) - set(new_files))

    manifest = {
        "version": args.version,
        "base_version": args.base,
        "files": entries,
        "deleted": deleted,
        "zip_sha256": _sha256(args.out),
        "zip_size": args.out.stat().st_size,
    }
    manifest_path = args.out.with_name(args.out.stem + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    full = sum(e["size"] for e in entries)
    print(f"update 包: {args.out.name}  {manifest['zip_size']/1024/1024:.1f} MB")
    print(f"变更文件: {len(entries)} 个（add {sum(1 for e in entries if e['action']=='add')} / "
          f"replace {sum(1 for e in entries if e['action']=='replace')}），删除 {len(deleted)} 个")
    print(f"变更总量(解包): {full/1024/1024:.1f} MB   manifest: {manifest_path.name}")
    print(f"对比全量安装包 259MB / 便携包 338MB —— 省下的就是没变的 Electron 壳与引擎运行时")


if __name__ == "__main__":
    main()
