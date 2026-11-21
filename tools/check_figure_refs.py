"""核对章节正文里的图号引用与 docs/figures/ 实际文件是否对得上。

规则（`docs/delivery/排版规范.md` §四）：
- 图注格式 `图 <章号>-<序号> <图名>（来源：...）`；
- 结构图必须给出 `docs/figures/svg/xxx.svg` 且文件存在；
- 缺图标 `（待补）`，正文保留引用——允许，但计入缺口清单；
- 正文引用（「如图 5-1 所示」）必须能找到同号图注，否则判为悬空引用。

用法：
    <python> tools/check_figure_refs.py [--root docs/delivery] [--out output/v017/figure_refs.txt]

退出码：0 无悬空引用且无缺失文件；1 有问题。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FIG_NUM = re.compile(r"图\s*(\d+)-(\d+)")
SVG_PATH = re.compile(r"(docs/figures/svg/[A-Za-z0-9_.\-]+\.svg)")
PENDING = ("待补",)

# 规范类文档里的图注是**示例**，不是真图注，不能按章节正文校验
SKIP = {"排版规范.md"}


def svg_exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def check(md: Path) -> tuple[list[str], list[str], int, int]:
    """返回 (问题列表, 缺口清单, 图注数, 正文引用数)。"""
    problems: list[str] = []
    gaps: list[str] = []
    captions: set[tuple[str, str]] = set()
    refs: list[tuple[str, str, int]] = []
    lines = md.read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines, 1):
        nums = FIG_NUM.findall(line)
        if not nums:
            continue
        is_caption = line.lstrip().startswith(">") and "来源" in line or (
            line.lstrip().startswith("图 ") and "-" in line
        )
        for ch, seq in nums:
            key = (ch, seq)
            svg = SVG_PATH.search(line)
            if svg:
                if not svg_exists(svg.group(1)):
                    problems.append(f"{md.name}:{i} 图 {ch}-{seq} 指向的文件不存在：{svg.group(1)}")
                captions.add(key)
            elif any(p in line for p in PENDING):
                gaps.append(f"{md.name}:{i} 图 {ch}-{seq} 待补")
                captions.add(key)
            elif is_caption:
                problems.append(f"{md.name}:{i} 图 {ch}-{seq} 图注缺来源标注（须给 svg 路径或标待补）")
                captions.add(key)
            else:
                refs.append((ch, seq, i))

    dangling = [(ch, seq, i) for ch, seq, i in refs if (ch, seq) not in captions]
    for ch, seq, i in dangling:
        problems.append(f"{md.name}:{i} 正文引用了图 {ch}-{seq}，但本章没有对应图注")
    return problems, gaps, len(captions), len(refs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="docs/delivery")
    ap.add_argument("--out", default="output/v017/figure_refs.txt")
    args = ap.parse_args()

    doc_root = ROOT / args.root
    mds = sorted(doc_root.glob("*.md"))
    if not mds:
        print(f"[FAIL] {doc_root} 下没有 md 文件")
        return 1

    problems: list[str] = []
    gaps: list[str] = []
    for md in mds:
        if md.name in SKIP:
            print(f"[SKIP] {md.name}（规范文档，图注为示例）")
            continue
        p, g, nc, nr = check(md)
        problems += p
        gaps += g
        print(f"[{'FAIL' if p else 'OK'}] {md.name}: 图注 {nc} 个，正文引用 {nr} 处，待补 {len(g)} 张")

    print(f"\n悬空/缺陷 {len(problems)} 处，待补图 {len(gaps)} 张")

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    body = []
    if problems:
        body.append("== 问题 ==")
        body += problems
    if gaps:
        body.append("== 待补清单 ==")
        body += gaps
    out.write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"明细已写入 {out.relative_to(ROOT).as_posix()}")

    for p in problems:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
