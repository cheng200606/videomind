"""核对前后端成对的上限常量是否一致（v0.17 P1-3）。

不硬编码期望值：从源文件正则提取四个常量再两两比较。
任一对不一致 -> exit 1，差异写进产物，供 CI / G 系列门槛断言。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

# (名称, 相对仓库根的路径, 正则) —— 正则捕获组 1 即常量数值
CHECKS = [
    ("SEARCH_LIMIT", "frontend/src/components/LibrarySearchPanel.vue",
     r"const\s+SEARCH_LIMIT\s*=\s*(\d+)"),
    ("_SEARCH_LIMIT", "backend/app/routers/knowledge.py",
     r"_SEARCH_LIMIT\s*=\s*(\d+)"),
    ("TRANSCRIPT_LIMIT", "frontend/src/views/WorkbenchView.vue",
     r"const\s+TRANSCRIPT_LIMIT\s*=\s*(\d+)"),
    ("_TRANSCRIPT_LIMIT", "backend/app/routers/parse.py",
     r"_TRANSCRIPT_LIMIT\s*=\s*(\d+)"),
]

# (前端常量名, 后端常量名) —— 必须相等的对
PAIRS = [
    ("SEARCH_LIMIT", "_SEARCH_LIMIT"),
    ("TRANSCRIPT_LIMIT", "_TRANSCRIPT_LIMIT"),
]


def extract(rel: str, pattern: str) -> tuple[int | None, str]:
    path = ROOT / rel
    if not path.is_file():
        return None, f"文件不存在: {rel}"
    hits = re.findall(pattern, path.read_text(encoding="utf-8"))
    if len(hits) != 1:
        return None, f"期望恰好 1 处赋值，实际 {len(hits)} 处: {rel}"
    return int(hits[0]), ""


def main() -> int:
    values: dict[str, int] = {}
    errors: list[str] = []
    for name, rel, pattern in CHECKS:
        value, err = extract(rel, pattern)
        if err:
            errors.append(f"{name}: {err}")
        else:
            values[name] = value

    results = []
    ok = not errors
    for fe, be in PAIRS:
        if fe in values and be in values:
            match = values[fe] == values[be]
            results.append({
                "pair": f"{fe} / {be}",
                "frontend": values[fe],
                "backend": values[be],
                "match": match,
            })
            if not match:
                ok = False
                errors.append(f"{fe}={values[fe]} 与 {be}={values[be]} 不一致")
        else:
            results.append({"pair": f"{fe} / {be}", "match": False, "error": "提取失败"})
            ok = False

    tz = timezone(timedelta(hours=8))
    report = {
        "name": "前后端上限常量一致性（v0.17 P1-3）",
        "at": datetime.now(tz).isoformat(timespec="seconds"),
        "ok": ok,
        "values": values,
        "pairs": results,
        "errors": errors,
    }
    out = ROOT / "output" / "v017" / "limits-check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[{report['name']}] {'PASS' if ok else 'FAIL'}")
    for r in results:
        if "error" in r:
            print(f"  {r['pair']}: {r['error']}")
        else:
            print(f"  {r['pair']}: {r['frontend']} == {r['backend']} -> {r['match']}")
    for e in errors:
        print(f"  ! {e}")
    print(f"[json] {out.relative_to(ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
