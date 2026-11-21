#!/usr/bin/env python
"""G5 文档红线词扫描（v0.17 质量门）。

扫 `docs/**/*.md` + 仓库根 `README.md` / `CHANGELOG.md` / `CONTRIBUTING.md`，
命中「首次」「唯一」「100% 准确」「完全自动」即报红。

**放行口径（组长 2026-11-21 定）**：白名单写死在本脚本里，且只允许一种命中放行——
命中的那一行本身是「规则自述行」，即该行在以约束语气引用这几个词（含 禁止/不得/红线 …
这类标记）。除此之外一律报红，没有按文件/按词的豁免表：加豁免等于承认"这句话看着像违规
但不算"，那种判断应该由人改文档，而不是让门学会闭眼。

用法（仓库根执行）：
    backend/.venv/Scripts/python tools/check_forbidden_words.py
    backend/.venv/Scripts/python tools/check_forbidden_words.py --json output/v017/g5.json

退出码：0 = 无未豁免命中；1 = 有；2 = 脚本自身出错。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 四个红线词；`100% 准确` 允许中间有无空格，两种写法都要抓
FORBIDDEN_RE = re.compile(r"100%\s*准确|首次|唯一|完全自动")

# 规则自述行的判定标记：同一行出现这些词，说明它在"立规矩"而不是"下断言"
RULE_MARKERS = [
    "禁止", "不得", "不许", "未确认前", "红线", "禁用词", "零处", "白名单",
]


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def scan() -> tuple[list[dict], list[dict], int]:
    targets: list[Path] = sorted(ROOT.glob("docs/**/*.md"))
    targets += [ROOT / n for n in ("README.md", "CHANGELOG.md", "CONTRIBUTING.md")]
    hits: list[dict] = []
    waived: list[dict] = []
    scanned = 0

    for path in targets:
        if not path.exists():
            continue
        scanned += 1
        rel = _rel(path)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            words = FORBIDDEN_RE.findall(line)
            if not words:
                continue
            if any(m in line for m in RULE_MARKERS):
                waived.append({"file": rel, "line": lineno, "words": words,
                               "why": "规则自述行（含约束标记）"})
                continue
            hits.append({"file": rel, "line": lineno, "words": words,
                         "text": line.strip()[:200]})
    return hits, waived, scanned


def main() -> int:
    ap = argparse.ArgumentParser(description="G5 文档红线词扫描")
    ap.add_argument("--json", help="把结果写成 JSON（一般放 output/v017/g5.json）")
    args = ap.parse_args()

    # Windows 控制台默认 GBK，命中行里的中文引号/破折号会 UnicodeEncodeError，
    # 把结论一起吞掉、只剩一个看不懂的 traceback。显式改 UTF-8 并降级替换。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    try:
        hits, waived, scanned = scan()
    except Exception as exc:                                   # noqa: BLE001
        print(f"[G5] 脚本自身出错：{exc}", file=sys.stderr)
        return 2

    for h in hits:
        print(f"{h['file']}:{h['line']}: {h['words']}")
        print(f"    {h['text']}")

    print()
    print(f"[G5] 扫描 {scanned} 个文件 · 规则自述行放行 {len(waived)} 处 · 未豁免 {len(hits)} 处")
    if hits:
        print("[G5] 失败：上面每一条都得改文档；本脚本没有按文件/按词的豁免表")
        code = 1
    else:
        print("[G5] 通过")
        code = 0

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"scanned": scanned, "hits": hits, "waived": waived, "ok": code == 0},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[G5] 结果已写入 {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
