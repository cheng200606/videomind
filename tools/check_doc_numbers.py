"""核对章节正文自报的数字与实际可复跑结果是否一致。

覆盖三类「必须对得上」的数字（体例样板 ch5 的做法）：
1. 测试用例数：正文写「后端 pytest 108」「前端 vitest 44」，脚本按
   `pytest --collect-only -q` 与 vitest 收集口径比对；
2. 表数：正文写「11 张表」，脚本数 `backend/app/models.py` 里 `table=True` 的类；
3. 枚举数：正文写「9 个枚举」，脚本数 `backend/app/enums.py` 里 `class *Enum` / `class *(str, Enum)`。

设计原则：**不跑全量测试**（慢且会与别人并行冲突），只做收集与静态计数——
快、无副作用、可反复跑。真实通过率由质量门的 G1/G2 负责。

用法：
    <python> tools/check_doc_numbers.py [--root docs/delivery] [--out output/v017/doc_numbers.txt]

退出码：0 全部一致；1 有偏差。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 正文里这些写法会被抓取比对
PYTEST_NUM = re.compile(r"后端\s*(?:pytest)?\s*[：:]?\s*\**\s*(\d{2,4})\s*(?:例|个用例|tests?)")
VITEST_NUM = re.compile(r"前端\s*(?:vitest)?\s*[：:]?\s*\**\s*(\d{2,4})\s*(?:例|个用例|tests?)")
# 前面不能紧跟数字或「–-」，否则「9–10 表」这种历史口径会被误抓成「10 张表」
TABLE_NUM = re.compile(r"(?<![\d–\-])(\d{1,2})\s*张?表(?![格数])")
ENUM_NUM = re.compile(r"(\d{1,2})\s*个枚举")


def count_models() -> int:
    text = (ROOT / "backend/app/models.py").read_text(encoding="utf-8")
    return len(re.findall(r"class\s+\w+\(SQLModel,\s*table=True\)", text))


def count_enums() -> int:
    text = (ROOT / "backend/app/enums.py").read_text(encoding="utf-8")
    return len(re.findall(r"^class\s+\w+\(str,\s*Enum\)", text, flags=re.MULTILINE))


def find_python() -> tuple[Path | None, str]:
    """找后端的解释器。

    `backend/.venv` 是 gitignore 的，**新建的 worktree 里没有**（实测在
    `.agents/worktrees/*` 里跑本脚本会直接找不到解释器）。此时回退到主工作树
    的 venv：解释器只是运行环境，被测代码仍取当前 worktree 里的那份，结论不失真。
    """
    candidates = [ROOT / "backend" / ".venv" / "Scripts" / "python.exe"]
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=str(ROOT),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if common.returncode == 0:
            main = Path(common.stdout.strip()).parent
            candidates.append(main / "backend" / ".venv" / "Scripts" / "python.exe")
    except Exception:  # noqa: BLE001
        pass
    for c in candidates:
        if c.is_file():
            return c, ""
    return None, "找不到解释器（已试 backend/.venv 与主工作树的 backend/.venv）"


def pytest_collected() -> tuple[int | None, str]:
    """只用 collect-only，不执行用例。

    返回 (收集数, 失败原因)。**收集失败必须如实上报，绝不能静默返回 None**——
    否则脚本会在没拿到数据的情况下判「偏差 0」，变成假绿。
    """
    py, err = find_python()
    if py is None:
        return None, err
    try:
        out = subprocess.run(
            [str(py), "-m", "pytest", "--collect-only", "-q"],
            cwd=str(ROOT / "backend"),
            capture_output=True,
            # 必须显式指定编码：pytest 输出里含中文（用例 docstring、路径），
            # 默认按 GBK 解码会抛 UnicodeDecodeError（实测 0xaa 无法解码）。
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"执行失败：{exc}"
    m = re.search(r"(\d+)\s+tests?\s+collected", out.stdout)
    if not m:
        tail = (out.stdout or out.stderr or "").strip().splitlines()[-1:] or [""]
        return None, f"输出里没有 collected 计数（末行：{tail[0][:120]}）"
    return int(m.group(1)), ""


def vitest_count() -> int | None:
    """数 spec 文件里的 it(/test( 定义数（参数化展开后的真实数由 vitest 报告）。"""
    base = ROOT / "frontend" / "src" / "__tests__"
    files = sorted(base.glob("*.spec.ts")) if base.is_dir() else []
    if not files:
        return None
    total = 0
    for f in files:
        total += len(re.findall(r"^\s*(?:it|test)\(", f.read_text(encoding="utf-8"), flags=re.MULTILINE))
    return total


def check_numbers_in_doc(
    rel: str, text: str, pattern: re.Pattern[str], actual: int | None, label: str
) -> list[str]:
    """用例数允许「基线 + 当日」两列并存。

    规则：正文里出现的每个数字，要么等于当日实际值，要么所在**同一行**带「基线」
    字样（表示它明示自己是历史值）。既不等于实际值、又没标基线的，判为过期数字。
    """
    if actual is None:
        return []
    out: list[str] = []
    for line in text.splitlines():
        for m in pattern.finditer(line):
            got = int(m.group(1))
            if got == actual:
                continue
            if "基线" in line:
                continue
            out.append(f"{rel} 写{label} {got} 例，当日实际为 {actual}（该行未标「基线」）")
    return out


def main() -> int:
    # 控制台默认 GBK 时，输出里的中文/符号会抛 UnicodeEncodeError 把结论吞掉
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="docs/delivery")
    ap.add_argument("--out", default="output/v017/doc_numbers.txt")
    args = ap.parse_args()

    actual_tables = count_models()
    actual_enums = count_enums()
    actual_pytest, pytest_err = pytest_collected()
    actual_vitest = vitest_count()

    print("== 实际值 ==")
    print(f"  models.py table=True 类：{actual_tables}")
    print(f"  enums.py 枚举类：{actual_enums}")
    print(f"  pytest collect-only：{actual_pytest if actual_pytest is not None else '（未取到）'}")
    print(f"  vitest 源定义数：{actual_vitest if actual_vitest is not None else '（未取到）'}")

    problems: list[str] = []
    # 取不到数就判失败，不许静默跳过——否则「没比对」会被读成「比对了且一致」，就是假绿。
    if actual_pytest is None:
        problems.append(f"后端用例数未能采集，本轮未做用例数校验（{pytest_err}）")
    doc_root = ROOT / args.root
    for md in sorted(doc_root.glob("*.md")):
        rel = md.relative_to(ROOT).as_posix()
        text = md.read_text(encoding="utf-8")

        for m in TABLE_NUM.finditer(text):
            got = int(m.group(1))
            # 只校验 8 以上的表数（「4 张表」这类可能指的是某一小节）
            if got < 8:
                continue
            if got != actual_tables:
                problems.append(f"{rel} 写「{got} 张表」，models.py 实为 {actual_tables}")

        for m in ENUM_NUM.finditer(text):
            got = int(m.group(1))
            if got != actual_enums:
                problems.append(f"{rel} 写「{got} 个枚举」，enums.py 实为 {actual_enums}")

        # 用例数允许「基线 + 当日」两列并存：正文必须出现当日实际值，
        # 其余数值须处于同一行里带「基线」字样，否则判为过期数字。
        if actual_pytest is not None:
            problems += check_numbers_in_doc(rel, text, PYTEST_NUM, actual_pytest, "后端")
        problems += check_numbers_in_doc(rel, text, VITEST_NUM, actual_vitest, "前端")

    problems = sorted(set(problems))
    print(f"\n偏差 {len(problems)} 处")

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(problems) + ("\n" if problems else ""), encoding="utf-8")
    print(f"明细已写入 {out.relative_to(ROOT).as_posix()}")
    for p in problems:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
