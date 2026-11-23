"""文档禁用词扫描（质量门 G5 的文档侧实现）。

红线来源：`docs/产品定义.md` §九 第 6 条与 `CONTRIBUTING.md` §八——
文档禁用无据表述「首次」「唯一」「100% 准确」「完全自动」。

难点是这些词在**规则条文本身**里必须出现（如「文档中禁止出现『首次』」），
在技术复述里也可能合法（如「唯一一级标题」）。所以白名单按「文件 + 行号 +
命中词」写死在本脚本里，并逐条给出理由；**新增豁免必须写理由**，否则不算数。

用法：
    <python> tools/check_doc_banned.py [--root docs] [--out output/v017/doc_banned.txt]

退出码：0 无白名单外命中；1 有命中。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BANNED = ["首次", "唯一", "100% 准确", "100%准确", "完全自动"]

# 白名单判据（v0.17 定稿，新增豁免必须按此判断并写理由）：
#   「唯一」用于「唯一出口 / 唯一权威 / 唯一路径」这类**排他性口径说明**时放行
#   （说的是「只有这一处定义」，是结构约束），
#   用于**宣称产品能力唯一性**时命中（说的是「只有我做到了」，是无据表述）。
#   两者区别在主语：主语是代码结构/文档口径 → 放行；主语是产品能力/效果 → 命中。
# 「首次 / 完全自动 / 100% 准确」无此豁免空间：只有在**红线条文本身**或
#   **描述流程先后顺序**（如「发版首次构建」）时才放行，绝不允许用于描述能力。
#
# (相对路径, 行号, 命中词, 理由)
# 行号用 0 表示「该文件任意行命中都豁免」——仅在整篇性质就是规则条文时使用。
WHITELIST: list[tuple[str, int, str, str]] = [
    ("docs/产品定义.md", 160, "首次", "红线条文本身，列举禁用词"),
    ("docs/产品定义.md", 160, "唯一", "红线条文本身，列举禁用词"),
    ("docs/产品定义.md", 160, "100% 准确", "红线条文本身，列举禁用词"),
    ("docs/产品定义.md", 160, "完全自动", "红线条文本身，列举禁用词"),
    ("docs/产品定义.md", 3, "唯一", "权威口径优先级声明，指口径不指功能唯一性"),
    ("docs/分工与任务卡.md", 4, "唯一", "角色职责口径，非产品能力宣称"),
    ("docs/分工与任务卡.md", 43, "唯一", "规则条文，引用红线"),
    ("docs/交付与排期.md", 160, "唯一", "风险条款表述，非能力宣称"),
    ("docs/桌面版发布方案.md", 27, "唯一", "描述打包内容物，非能力宣称"),
    ("docs/桌面版发布方案.md", 28, "首次", "描述发版流程先后顺序"),
    ("docs/桌面版发布方案.md", 67, "首次", "描述更新器行为顺序"),
    ("docs/迭代方案_v0.13.md", 8, "唯一", "指 labels.ts 是枚举中文映射的单一口径"),
    ("docs/迭代方案_v0.15.md", 15, "唯一", "指配置项单一口径"),
    ("docs/迭代方案_v0.16.md", 30, "唯一", "指 theme.css 是颜色 token 单一口径"),
    ("docs/迭代方案_v0.16.md", 63, "唯一", "指页面仅一个一级标题（heading-order 规范）"),
    ("docs/delivery/排版规范.md", 75, "首次", "描述正文引用图的时机，非能力宣称"),
    ("docs/delivery/v0.17_ch5_系统实现与测试.md", 285, "唯一", "「唯一约束」是数据库术语"),
    ("docs/delivery/v0.17_ch5_系统实现与测试.md", 361, "唯一", "「未设唯一」指未建唯一索引，数据库术语"),
    ("CONTRIBUTING.md", 13, "唯一", "「唯一代码与文档版本库」指单一仓库，非产品能力宣称"),
    ("CONTRIBUTING.md", 38, "唯一", "「唯一路径」指协作流程单一路径，非产品能力宣称"),
    ("AGENTS.md", 8, "唯一", "「枚举中文映射唯一出口」指代码结构单一口径，非产品能力宣称"),
    ("docs/README.md", 13, "唯一", "「风险的唯一出处」是排他性口径说明，指单一出处，非产品能力宣称"),
]

# 历史记录类文件不做正文审查：它们记录的是当时发生过的事实
HISTORICAL = [
    "CHANGELOG.md",
    "docs/HANDOFF-",
    "docs/测试与迭代报告_",
    "docs/补充验证与首屏优化_",
    "docs/迭代方案_",
]

# 数据库术语里的「唯一」不是禁用词
UNIQUE_TERM = re.compile(r"(?:唯一\s*(?:约束|索引|键|性)|未设\s*唯一|非唯一|唯一性约束)")


# 全仓模式排除的目录（相对仓库根）。.agents/ 里是其他成员的 worktree 副本，
# 内容是旧版本，扫进来只会报假阳性，且会随谁新开 worktree 而随机变红。
EXCLUDE_DIRS = (
    ".agents/",
    ".venv/",
    "node_modules/",
    "output/",
    "backend/data/",
    ".git/",
    "release/",
    "dist/",
    # `.qoder/` 是本地工具生成的仓库 wiki（`.gitignore:22` 已忽略、`git ls-files` 0 命中），
    # 不是我们的交付文档；不排除的话全仓模式会报 55 处假阳性把它淹没。
    ".qoder/",
)


def is_excluded(md: Path) -> bool:
    rel = md.relative_to(ROOT).as_posix()
    return any(rel.startswith(d) or f"/{d}" in f"/{rel}" for d in EXCLUDE_DIRS)


def is_historical(rel: str) -> bool:
    return any(rel.startswith(h) or rel == h for h in HISTORICAL)


def whitelisted(rel: str, lineno: int, word: str) -> bool:
    for w_rel, w_line, w_word, _reason in WHITELIST:
        if w_rel != rel or w_word != word:
            continue
        if w_line == 0 or w_line == lineno:
            return True
    return False


def is_rule_quote(line: str, word: str) -> bool:
    """规则条文里「列举禁用词」的写法，两种形态都算引用而非使用。

    ① 词被 「」/“”/（）单独括住：`禁止出现「首次」「唯一」等无据表述`
    ② 一行内枚举多个词并配执法语：`零处「首次 / 唯一 / 100% 准确 / 完全自动」表述`

    判定必须同时满足「被引号括住」+「行内有禁止/零容忍类措辞」，
    避免把真正违规的叙述句也放过。
    """
    enforcement = (
        "禁止",
        "不得",
        "零处",
        "零命中",
        "禁用",
        "杜绝",
        "不得出现",
        "未出现",  # PR 模板的检查句式：「文档中未出现无据表述（首次 / 唯一 / ...）」
        "不使用",  # 原型线《AI使用声明》：「文档中不使用「首次」「唯一」…等表述」
    )
    if not any(e in line for e in enforcement):
        return False
    for left, right in (("「", "」"), ("“", "”"), ("\"", "\""), ("（", "）"), ("(", ")")):
        start = line.find(left)
        while start != -1:
            end = line.find(right, start + 1)
            if end == -1:
                break
            inner = line[start + 1 : end].strip()
            if inner == word:
                return True
            # ② 枚举形态：把括内按分隔符拆开逐项比
            parts = re.split(r"\s*[/、，,]\s*", inner)
            if word in [p.strip() for p in parts] and len(parts) > 1:
                return True
            start = line.find(left, end + 1)
    return False


def main() -> int:
    # 命中行可能含 ✓/✗/箭头等非 GBK 字符（来自被扫描文件的正文），
    # 控制台默认 GBK 会 UnicodeEncodeError 把真实结论吞掉，故统一转 UTF-8。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="docs")
    ap.add_argument(
        "--full",
        action="store_true",
        help="全仓兜底模式：扫描仓库全部 md，排除 .agents/.venv/node_modules/output/backend/data（合稿前一次性用）",
    )
    ap.add_argument("--out", default="output/v017/doc_banned.txt")
    args = ap.parse_args()

    targets: list[Path] = []
    if args.full:
        # 全仓模式：别人新开一个 worktree 不应该让这道门变红，故排除 .agents/；
        # 依赖目录与运行产物同理排除（它们不是文档，扫出来的也不是我们的问题）。
        targets += sorted(ROOT.rglob("*.md"))
        targets = [t for t in targets if not is_excluded(t)]
    else:
        # 默认窄模式：只扫文档目录与三份根级规约文件。
        doc_root = ROOT / args.root
        targets += sorted(doc_root.rglob("*.md"))
        for name in ("README.md", "CONTRIBUTING.md", "AGENTS.md"):
            p = ROOT / name
            if p.is_file():
                targets.append(p)

    hits: list[str] = []
    skipped: list[str] = []
    scanned = 0

    for md in targets:
        rel = md.relative_to(ROOT).as_posix()
        if is_historical(rel):
            skipped.append(rel)
            continue
        scanned += 1
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for word in BANNED:
                if word not in line:
                    continue
                if whitelisted(rel, i, word):
                    continue
                if is_rule_quote(line, word):
                    continue
                if word == "唯一" and UNIQUE_TERM.search(line):
                    continue
                hits.append(f"{rel}:{i} 「{word}」 → {line.strip()[:100]}")

    print(f"扫描 {scanned} 个文件，跳过 {len(skipped)} 个历史记录文件")
    print(f"命中 {len(hits)} 处（白名单外）")

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(hits) + ("\n" if hits else ""), encoding="utf-8")
    print(f"明细已写入 {out.relative_to(ROOT).as_posix()}")

    for h in hits:
        print("  " + h)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
