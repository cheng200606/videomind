"""GitHub Release 发布单命令工具：建 Release + 流式传资产 + 逐一核验。

用法（仓库根目录，backend venv 或任意装有 httpx 的 python）：
  backend/.venv/Scripts/python desktop/publish_release.py \
      --tag v0.13.0 \
      --notes desktop/release/notes-v0.13.0.md \
      --assets "desktop/release/VideoMind-Setup-0.13.0.exe" \
               "desktop/release/latest.yml" \
               "desktop/release/VideoMind-Setup-0.13.0.exe.blockmap" \
               "desktop/release/VideoMind-0.13.0-win64.zip"

行为约定：
  - PAT 从 git credential fill 读取：不回显、不落盘、不进命令行参数
  - Release 已存在（按 tag 查）则复用，不改已有说明；不存在则创建（target_commitish develop）
  - 同名资产：远端字节数与本地一致 → 跳过；不一致 → 先删后传（避免半截损坏文件）
  - 结束前带鉴权核验全部资产 state=uploaded，打印 release URL 与资产直链
"""

import argparse
import subprocess
import sys
from pathlib import Path

import httpx

REPO = "cheng200606/videomind"
API = f"https://api.github.com/repos/{REPO}"
UPLOAD = f"https://uploads.github.com/repos/{REPO}/releases"
_CONTENT_TYPES = {
    ".exe": "application/octet-stream",
    ".zip": "application/zip",
    ".yml": "text/yaml",
    ".blockmap": "application/octet-stream",
    ".sha256": "text/plain",
}


def _token() -> str:
    cred = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True,
    ).stdout
    for line in cred.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("git credential fill 未返回 password——请先在本机推送过一次 GitHub")


def _get_release(client: httpx.Client, tag: str) -> dict | None:
    r = client.get(f"{API}/releases/tags/{tag}")
    if r.status_code == 200:
        return r.json()
    if r.status_code == 404:
        return None
    raise SystemExit(f"查询 Release 失败 {r.status_code}: {r.text[:300]}")


def _ensure_release(client: httpx.Client, tag: str, notes_path: Path | None) -> dict:
    existing = _get_release(client, tag)
    if existing:
        print(f"release 复用: {existing['html_url']}")
        return existing
    body = notes_path.read_text(encoding="utf-8") if notes_path else ""
    r = client.post(API + "/releases", json={
        "tag_name": tag, "target_commitish": "develop",
        "name": tag, "body": body, "draft": False, "prerelease": False,
    })
    if r.status_code not in (201, 200):
        raise SystemExit(f"创建 Release 失败 {r.status_code}: {r.text[:300]}")
    print(f"release 创建: {r.json()['html_url']}")
    return r.json()


def _upload(client: httpx.Client, release_id: int, path: Path) -> None:
    name = path.name
    size = path.stat().st_size
    existing = client.get(f"{API}/releases/{release_id}/assets")
    for asset in existing.json():
        if asset["name"] == name:
            if asset["size"] == size:
                print(f"asset 跳过（字节一致）: {name}")
                return
            print(f"asset 远端尺寸不一致，删除重传: {name}（远端 {asset['size']} ≠ 本地 {size}）")
            client.delete(f"{API}/releases/assets/{asset['id']}").raise_for_status()
            break
    with path.open("rb") as f:
        r = client.post(f"{UPLOAD}/{release_id}/assets", params={"name": name},
                        headers={"Content-Type": _CONTENT_TYPES.get(path.suffix.lower(),
                                                                 "application/octet-stream")},
                        content=f, timeout=1800)
    if r.status_code >= 300:
        raise SystemExit(f"上传失败 {name} {r.status_code}: {r.text[:300]}")
    print(f"asset 上传: {name} ({size} bytes)")


def _verify(client: httpx.Client, tag: str, names: list[str]) -> None:
    rel = _get_release(client, tag)
    assert rel is not None, "核验时 Release 不见了"
    assets = {a["name"]: a["state"] for a in rel["assets"]}
    bad = [n for n in names if assets.get(n) != "uploaded"]
    if bad:
        raise SystemExit(f"核验失败，未达 uploaded: {bad}（现有 {assets}）")
    print("核验通过，全部资产 state=uploaded:")
    for n in names:
        print(f"  {n} -> {rel['html_url']}/downloads/{n}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", required=True, help="形如 v0.13.0")
    ap.add_argument("--notes", type=Path, default=None, help="Markdown 说明文件（Release 已存在时忽略）")
    ap.add_argument("--assets", nargs="+", type=Path, required=True)
    args = ap.parse_args()

    for p in args.assets:
        if not p.is_file():
            raise SystemExit(f"资产不存在: {p}")

    headers = {"Authorization": f"Bearer {_token()}",
               "Accept": "application/vnd.github+json"}
    with httpx.Client(headers=headers, timeout=60) as client:
        rel = _ensure_release(client, args.tag, args.notes)
        for p in args.assets:
            _upload(client, rel["id"], p)
        _verify(client, args.tag, [p.name for p in args.assets])


if __name__ == "__main__":
    main()
