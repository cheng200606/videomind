"""核对 docs/delivery/ 下章节正文里的 `文件:行号` 引用是否仍然成立。

背景：ch5/ch4 的体例要求「每条行为可指 文件:行号」。代码一改行号就漂移，
文档却不会自己报错，所以用脚本兜住。

用法（仓库根目录）：
    <python> tools/check_doc_refs.py [--root docs/delivery] [--out output/v017/doc_refs.txt]

退出码：0 全部命中；1 有失效引用（文件不存在 / 行号越界）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 匹配 `backend/app/pipeline.py:291` 或 `pipeline.py:291-300` 这类引用
# 路径字符集必须含中文：仓库里 `docs/迭代方案_v0.16.md`、`docs/数据字典.md` 这类
# 文件名带汉字，只写 ASCII 会把 `docs/迭代方案_v0.16.md:17` 截成 `_v0.16.md:17`
# 并误报「文件不存在」（实测）。注意 `path` 组必须整体只出现一次，
# 写成 `(?P<path>段)*` 会让 group 取到 None（TypeError: Path / None）。
_CH = r"(?:[A-Za-z0-9_.\-]|[\u4e00-\u9fff])"
REF = re.compile(
    rf"`?(?P<path>(?:{_CH}+/)*{_CH}+\.(?:py|ts|vue|js|json|md|spec\.ts))"
    r":(?P<start>\d+)(?:\s*[-–~]\s*(?P<end>\d+))?`?"
)


def resolve(path_text: str) -> Path | None:
    """把文档里的相对路径解析到仓库内实际文件。

    文档里可能写 basename（`pipeline.py:291`）也可能写相对路径
    （`backend/app/pipeline.py:291`），逐个候选试探。
    """
    candidates = [ROOT / path_text]
    # 带子目录的简写（`engines/frames.py`、`api/client.ts`）先挂到常见根下再判；
    # `交付与排期.md:107` 这类省略了 `docs/` 前缀的写法也要认（章内引用很常见）
    for prefix in ("backend", "backend/app", "frontend", "frontend/src", "desktop", "docs"):
        candidates.append(ROOT / prefix / path_text)
    if "/" not in path_text:
        candidates += [
            ROOT / "backend" / "app" / path_text,
            ROOT / "backend" / "app" / "engines" / path_text,
            ROOT / "backend" / "app" / "routers" / path_text,
            ROOT / "backend" / "tests" / path_text,
            ROOT / "frontend" / "src" / path_text,
            ROOT / "frontend" / "src" / "api" / path_text,
            ROOT / "frontend" / "src" / "composables" / path_text,
            ROOT / "frontend" / "src" / "__tests__" / path_text,
        ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def check_file(md: Path) -> list[str]:
    problems: list[str] = []
    lines = md.read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(lines, 1):
        for m in REF.finditer(line):
            raw = m.group("path")
            start = int(m.group("start"))
            end = int(m.group("end")) if m.group("end") else start
            target = resolve(raw)
            if target is None:
                problems.append(f"{md.name}:{lineno} 文件不存在：{raw}")
                continue
            total = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
            if start < 1 or end > total:
                rel = target.relative_to(ROOT).as_posix()
                problems.append(
                    f"{md.name}:{lineno} 行号越界：{rel}:{start}-{end}（实际 {total} 行）"
                )
    return problems


def main() -> int:
    # 控制台默认 GBK 时，输出里的中文/符号会抛 UnicodeEncodeError 把结论吞掉
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="docs/delivery")
    ap.add_argument("--out", default="output/v017/doc_refs.txt")
    args = ap.parse_args()

    doc_root = ROOT / args.root
    mds = sorted(doc_root.glob("*.md"))
    if not mds:
        print(f"[FAIL] {doc_root} 下没有 md 文件")
        return 1

    all_problems: list[str] = []
    total_refs = 0
    for md in mds:
        before = len(all_problems)
        all_problems += check_file(md)
        count = len(REF.findall(md.read_text(encoding="utf-8")))
        total_refs += count
        status = "OK" if len(all_problems) == before else "FAIL"
        print(f"[{status}] {md.name}: {count} 处引用")

    print(f"\n合计 {total_refs} 处 `文件:行号` 引用，{len(all_problems)} 处失效")

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(all_problems) + ("\n" if all_problems else ""), encoding="utf-8"
    )
    print(f"明细已写入 {out.relative_to(ROOT).as_posix()}")

    if all_problems:
        for p in all_problems:
            print("  " + p)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
