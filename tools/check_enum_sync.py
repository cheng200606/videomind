#!/usr/bin/env python
"""G6 前后端枚举同源校验（v0.17 质量门）。

AGENTS.md 定的规矩：后端加新枚举要同步补 `frontend/src/api/labels.ts` 的中文映射表；
`REVISION_TRANSITIONS` 两端必须同源。规矩在人脑里，代码不会自己报错——这个脚本把它变成
一条命令：**直接从源码里读值再逐项比对**，不依赖注释、不依赖人肉核对。

比对三类：
  1. Python `class X(str, Enum)` 的成员值  ↔  `types.ts` 的 `export type X = 'a' | 'b'`
     以及 `export const XS = [...] as const`
  2. `enums.REVISION_TRANSITIONS` 的合法跳转表  ↔  `labels.ts` 的 `REVISION_TRANSITIONS`
  3. `labels.ts` 里每张 `*_LABEL` 表的 key 必须能被某个后端枚举值覆盖
     （防止后端删值、前端表留残留）

用法（仓库根执行）：
    backend/.venv/Scripts/python tools/check_enum_sync.py
    backend/.venv/Scripts/python tools/check_enum_sync.py --json output/v017/g6.json

退出码：0 = 全对齐；1 = 有差异；2 = 脚本自身出错（例如源码结构变了要跟着改解析）。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENUMS_PY = ROOT / "backend" / "app" / "enums.py"
TYPES_TS = ROOT / "frontend" / "src" / "api" / "types.ts"
LABELS_TS = ROOT / "frontend" / "src" / "api" / "labels.ts"

# labels.ts 里的中文映射表 → 它应该覆盖哪个后端枚举
LABEL_TABLES = {
    "STATUS_LABEL": ["BatchStatus", "VideoStatus"],
    "STAGE_LABEL": ["Stage"],
    "STAGE_STATUS_LABEL": ["StageStatus"],
    "ARTIFACT_LABEL": ["ArtifactType"],
    "CONFIDENCE_LABEL": ["Confidence"],
    "REVISION_LABEL": ["RevisionState"],
}

# 后端枚举 → 前端用哪个类型承接。前端暂时没有命名的就显式登记在这里，
# 附一句为什么可以这么承接，避免"找不到就当没差异"糊过去。
ALIASES = {
    "BatchStatus": ("VideoStatus",
                    "BatchState.status / BatchSummary.status 直接复用 VideoStatus，"
                    "两者取值集合完全相同（pending/running/succeeded/partial/failed）"),
}

# 前端没有命名类型、但代码里以字面量联合出现的位置
INLINE_UNIONS = {
    "TagTarget": ("frontend/src/api/client.ts", r"'video'\s*\|\s*'item'",
                  "client.ts 的 listTags / bindTag / dismissTag 参数用内联字面量联合"),
}


# ── 后端：ast 解析，不 import（避免触发 Settings / 引擎注册副作用）
def read_backend_enums() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    tree = ast.parse(ENUMS_PY.read_text(encoding="utf-8"))
    enums: dict[str, list[str]] = {}
    transitions: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            values: list[str] = []
            for stmt in node.body:
                # TRANSCRIBE = "transcribe"
                if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Name)
                        and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)):
                    values.append(stmt.value.value)
            if values:
                enums[node.name] = values
        # REVISION_TRANSITIONS: dict[RevisionState, tuple[...]] = {...}
        if (isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "REVISION_TRANSITIONS"
                and isinstance(node.value, ast.Dict)):
            for k, v in zip(node.value.keys, node.value.values):
                if not isinstance(k, ast.Attribute):
                    continue
                key = k.attr.lower()          # PENDING_CONFIRM -> pending_confirm
                if isinstance(v, ast.Tuple):
                    transitions[key] = [e.attr.lower() for e in v.elts
                                        if isinstance(e, ast.Attribute)]
    return enums, transitions


# ── 前端：正则解析 type 联合 / as const 数组
def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"^\s*//.*$", "", text, flags=re.M)


def read_frontend(ts: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    ts = _strip_comments(ts)
    unions: dict[str, list[str]] = {}
    arrays: dict[str, list[str]] = {}

    # export type Stage = 'transcribe' | 'visual' | ...
    for m in re.finditer(r"export type (\w+) =([^;\n]+)", ts):
        name, body = m.group(1), m.group(2).strip()
        if "'" not in body and '"' not in body:
            continue                       # 不是字面量联合，跳过（如 Record<...>）
        vals = re.findall(r"['\"]([^'\"]+)['\"]", body)
        if vals:
            unions[name] = vals

    # export const STAGE_STATUSES = ['pending', ...] as const
    for m in re.finditer(r"export const (\w+)(?::[^=]+)? =\s*\[([^\]]*)\]", ts):
        arrays[m.group(1)] = re.findall(r"['\"]([^'\"]+)['\"]", m.group(2))

    # export const REVISION_TRANSITIONS: Record<string, string[]> = { draft: ['pending_confirm'], ... }
    # 注意类型注解可有可无，别把 `: Record<...>` 当成匹配失败的理由
    for m in re.finditer(r"export const (\w+)\s*(?::[^=]+)?=\s*\{([^}]*)\}", ts):
        body = m.group(2)
        table: dict[str, list[str]] = {}
        for tm in re.finditer(r"(\w+):\s*\[([^\]]*)\]", body):
            table[tm.group(1)] = re.findall(r"['\"]([^'\"]+)['\"]", tm.group(2))
        if table:
            arrays[f"__TABLE__{m.group(1)}"] = table  # type: ignore[assignment]
    return unions, arrays


def _enum_key_candidates(name: str) -> list[str]:
    """StageStatus → STAGE_STATUSES / STAGE_STATUSS / STAGESTATUSES / StageStatusS 都试。

    前端习惯是 `<SCREAMING_SNAKE>S`，Python 类名是 CamelCase，
    必须先拆驼峰再拼，直接 upper() 会得到 STAGESTATUSES 这种不存在的东西。
    末尾已经是 S 的词（STATUS）复数要加 ES：STAGE_STATUS → STAGE_STATUSES。
    """
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()
    out = []
    if snake.endswith("S"):
        out.append(f"{snake}ES")
    out += [f"{snake}S", f"{name.upper()}S", f"{name}S"]
    return out


def read_label_table_keys(ts: str, table: str) -> set[str]:
    """取某张 *_LABEL 表的 key 集合（含 REVISION_TRANSITIONS 这类字面量表）。"""
    ts = _strip_comments(ts)
    m = re.search(rf"export const {table}\b[^=]*=\s*\{{(.*?)\n\}}", ts, flags=re.S)
    if not m:
        return set()
    body = re.sub(r"\.\.\.\w+,?", "", m.group(1))        # 展开运算符不算本表 key
    return set(re.findall(r"(?:^|[,{{\s])(\w+)\s*:", body))


def main() -> int:
    ap = argparse.ArgumentParser(description="G6 前后端枚举同源校验")
    ap.add_argument("--json", help="把结果写成 JSON（一般放 output/v017/g6.json）")
    args = ap.parse_args()

    # 同 G5：Windows 控制台默认 GBK，差异行里的中文/✓ 会 UnicodeEncodeError 吞掉结论。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    try:
        be_enums, be_trans = read_backend_enums()
        unions, arrays = read_frontend(TYPES_TS.read_text(encoding="utf-8"))
        labels_ts = LABELS_TS.read_text(encoding="utf-8")
        # 状态机跳转表在 labels.ts 里，不在 types.ts，要单独解一次
        _, label_arrays = read_frontend(labels_ts)
        fe_trans = label_arrays.get("__TABLE__REVISION_TRANSITIONS", {})
    except Exception as exc:                                   # noqa: BLE001
        print(f"[G6] 解析失败（源码结构可能变了，需同步改本脚本）：{exc}", file=sys.stderr)
        return 2

    problems: list[str] = []
    checked = 0

    # 1) 枚举值逐项比对：前端来源优先级 → 同名 type 联合 > 别名类型 > 常量数组 > 内联字面量
    for name, values in sorted(be_enums.items()):
        fe: list[str] | None = None
        fe_src = f"types.ts type {name}"

        if name in unions:
            fe = unions[name]
        elif name in ALIASES:
            alias, why = ALIASES[name]
            fe = unions.get(alias)
            fe_src = f"types.ts type {alias}（{name} 的承接类型；{why}）"
        else:
            for key in _enum_key_candidates(name):
                if key in arrays:
                    fe = arrays[key]
                    fe_src = f"types.ts const {key}"
                    break

        if fe is None and name in INLINE_UNIONS:
            rel, pattern, why = INLINE_UNIONS[name]
            src = (ROOT / rel).read_text(encoding="utf-8")
            if re.search(pattern, src):
                # 内联联合里逐个值确认都在（'video' | 'item' 这种）
                found = [v for v in values if f"'{v}'" in src or f'"{v}"' in src]
                fe = found
                fe_src = f"{rel} 内联联合（{why}）"

        if fe is None:
            problems.append(f"后端枚举 {name} 在前端找不到对应类型/常量数组/内联联合")
            continue
        checked += 1
        missing = [v for v in values if v not in fe]
        extra = [v for v in fe if v not in values]
        if missing:
            problems.append(f"{name}: 前端 {fe_src} 缺 {missing}（后端有：{values}）")
        if extra:
            problems.append(f"{name}: 前端 {fe_src} 多出 {extra}（后端没有）")

    # 2) REVISION_TRANSITIONS 同源
    if be_trans:
        checked += 1
        if not fe_trans:
            problems.append("labels.ts 里没有可解析的 REVISION_TRANSITIONS 字面量表")
        else:
            for key in sorted(set(be_trans) | set(fe_trans)):
                b = sorted(be_trans.get(key, []))
                f = sorted(fe_trans.get(key, []))
                if b != f:
                    problems.append(
                        f"REVISION_TRANSITIONS[{key}] 不同源：后端 {b} / 前端 {f}")
                else:
                    checked += 1

    # 3) labels.ts 的中文表 key 必须被后端枚举值覆盖（残留检测）
    all_values = {v for vals in be_enums.values() for v in vals}
    # 事件流专用 key 不在后端枚举里：batch / video_start / video_failed 是合成事件
    synthetic = {"batch", "video_start", "video_failed"}
    for table, owners in LABEL_TABLES.items():
        keys = read_label_table_keys(labels_ts, table)
        if not keys:
            problems.append(f"labels.ts 里找不到 {table}")
            continue
        checked += 1
        orphan = sorted(keys - all_values - synthetic)
        if orphan:
            owners_desc = " / ".join(owners)
            problems.append(
                f"{table} 有后端枚举里不存在的 key：{orphan}（应属 {owners_desc}）")

    for p in problems:
        print(f"  ✗ {p}")

    print()
    print(f"[G6] 后端枚举 {len(be_enums)} 类 · 比对 {checked} 项 · 差异 {len(problems)} 处")
    if problems:
        print("[G6] 失败：上面每一条都要在两边同步改掉")
        code = 1
    else:
        print("[G6] 通过：前后端枚举与状态机跳转表同源")
        code = 0

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "ok": code == 0,
            "checked": checked,
            "backend_enums": be_enums,
            "backend_transitions": be_trans,
            "frontend_transitions": fe_trans,
            "problems": problems,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[G6] 结果已写入 {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
