#!/usr/bin/env python
"""辅图 1 · 技术路线图（建议置于 ch1 项目概述，或 ch2 可行性分析）

上半：从「选题 → 双通道解析 → 结构化 → 证据链 → 导出」五个环节的技术演进，
      每条能力用 ● 已实现 / ○ 设计中 标注落地状态。
下半：版本里程碑轴，标出每个版本补上的关键能力（口径见 CHANGELOG 与 AGENTS.md）。
口径与代码同源：backend/app/{enums,artifacts,llm,pipeline,export}.py、
frontend/src/views/、docs/交付与排期.md §4.2。

重新生成（在仓库根目录执行）：
    python docs/figures/src/fig-aux1-tech-roadmap.py
产物：docs/figures/svg/fig-aux1-tech-roadmap.svg（按 LF 写入，勿手改 SVG）
"""
from pathlib import Path
from html import escape

W, H = 1800, 1000
FONT = "Source Han Sans CN, Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif"
out = []


def add(s):
    out.append(s)


def text(x, y, s, size=12, weight="normal", fill="#0F172A", anchor="start"):
    add(
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>'
    )


def rect(x, y, w, h, fill, stroke, rx=0, sw=1):
    add(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
    )


def line(pts, stroke="#64748B", sw=1.1, dash=None, marker_end=None, marker_start=None):
    d = ' stroke-dasharray="5 4"' if dash else ''
    me = f' marker-end="url(#{marker_end})"' if marker_end else ''
    ms = f' marker-start="url(#{marker_start})"' if marker_start else ''
    p = " ".join(f"{x},{y}" for x, y in pts)
    add(
        f'<polyline points="{p}" fill="none" stroke="{stroke}" stroke-width="{sw}"'
        f'{d}{me}{ms} stroke-linejoin="round"/>'
    )


def ulen(s):
    return sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in s)


def wrap(s, maxu):
    """折行：以空格为优先断点，避免把 ASCII 单词从中间劈开。"""
    words, cur = [], ""
    for ch in s:
        if ch == " ":
            if cur:
                words.append(cur)
                cur = ""
            words.append(" ")
        else:
            cur += ch
    if cur:
        words.append(cur)

    lines, line = [], ""
    for w in words:
        if ulen(line + w) > maxu and line.strip():
            lines.append(line.rstrip())
            line = "" if w == " " else w
        else:
            line += w
    if line.strip():
        lines.append(line.rstrip())
    # 词本身超长（无空格长串）时才退化为逐字硬切
    fixed = []
    for ln in lines:
        while ulen(ln) > maxu:
            cut, acc = "", 0.0
            for ch in ln:
                step = 1.0 if ord(ch) > 0x2E80 else 0.55
                if acc + step > maxu:
                    break
                cut += ch
                acc += step
            fixed.append(cut)
            ln = ln[len(cut):]
        fixed.append(ln)
    return [ln for ln in fixed if ln]


add(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}" font-family="{FONT}">'
)
add(
    '''<defs>
<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
 orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" fill="none" stroke="#64748B"
 stroke-width="1.2"/></marker>
</defs>'''
)
rect(0, 0, W, H, "#FFFFFF", "#FFFFFF")

text(30, 40, "辅图 1 · 技术路线：从选题到可带走的证据链", 18, "bold", "#0F172A")
text(
    30,
    64,
    "上排为五个技术环节的演进路线，下排为版本里程碑；● 已实现并入库，○ 设计中或本期不实施。",
    11,
    "normal",
    "#64748B",
)

# ── 上排：五环节 ─────────────────────────────────────────────
TITLES = [
    ("① 选题与范围锁定", "2026-11-05 冻结"),
    ("② 双通道解析", "AsrEngine / OcrEngine"),
    ("③ 结构化", "llm.structure 分块合并"),
    ("④ 证据链", "Evidence 一等实体"),
    ("⑤ 导出与交付", "可带走、可追溯"),
]
BULLETS = [
    [
        "本地知识 / 讲解类视频批量结构化",
        "红线：不做注册权限、上云、并发队列、向量检索、视频下载",
        "11 张表口径统一（Tag 与 TagBinding 分列）",
        "8 张 UML + 4 张辅图，图源双入库",
        "○ F5 课程版增强（仅设计）",
    ],
    [
        "ASR：Mock / Whisper / Yueying / FunASR",
        "OCR：RapidOCR / PaddleOCR / VisionModel",
        "抽帧 + 均值差去重（Pillow + numpy）",
        "转写缓存键带引擎档位",
        "mock 只回放同名样例，绝不冒充",
        "○ F5 语音-视觉交叉校验（本期不实现）",
    ],
    [
        "DeepSeek 或任意 OpenAI 兼容 base_url",
        "分块输入时间归零，只出相对毫秒",
        "_rebase_draft 合并回移并夹取",
        "截断先 _salvage_truncated 抢救",
        "report 带回截断事实，不静默丢",
        "无 Key 降级规则草稿并标注",
    ],
    [
        "时间戳 + 原话 + 片段帧 + 通道",
        "ItemDraft 统一中间态",
        "channel 区分 asr / ocr / both",
        "置信度三级：明述 / 推断 / 低置信",
        "ConflictRecord 留痕通道冲突",
        "覆盖提示随导出物带走",
    ],
    [
        "批次级 Markdown：章节 + 知识点 + 时间码",
        "coverage_notices 单一口径",
        "/structured 供第三方插件",
        "桌面版 NSIS + 便携 ZIP",
        "○ 增量更新应用端（本期不实施）",
        "○ C 级引擎运行时分离（顺延）",
    ],
]

CARD_W, GAP, X0 = 328, 24, 30
centers = [X0 + i * (CARD_W + GAP) + CARD_W / 2 for i in range(len(TITLES))]

line([(centers[0], 100), (centers[-1], 100)], stroke="#CBD5E1", sw=2)
for i in range(len(centers) - 1):
    line([(centers[i] + 26, 100), (centers[i + 1] - 26, 100)], marker_end="arrow")
for i, cx in enumerate(centers):
    add(f'<circle cx="{cx}" cy="100" r="15" fill="#EEF2FF" stroke="#4338CA" stroke-width="1.2"/>')
    text(cx, 105, str(i + 1), 13, "bold", "#4338CA", "middle")

CARD_Y, CARD_H = 138, 300
for i, (title, sub) in enumerate(TITLES):
    x = X0 + i * (CARD_W + GAP)
    rect(x, CARD_Y, CARD_W, CARD_H, "#FFFFFF", "#4338CA", 8, 1.2)
    rect(x, CARD_Y, CARD_W, 62, "#EEF2FF", "#EEF2FF", 8, 1)
    rect(x, CARD_Y + 46, CARD_W, 16, "#EEF2FF", "#EEF2FF", 0, 0)
    line([(x, CARD_Y + 62), (x + CARD_W, CARD_Y + 62)], stroke="#4338CA", sw=1)
    text(x + 16, CARD_Y + 27, title, 14.5, "bold", "#0F172A")
    text(x + 16, CARD_Y + 49, sub, 10.5, "normal", "#475569")

    y = CARD_Y + 88
    for b in BULLETS[i]:
        done = not b.startswith("○")
        body = b[2:] if b[0] in "○●" else b
        text(x + 16, y, "●" if done else "○", 11, "bold", "#4338CA" if done else "#B45309")
        tcolor = "#334155" if done else "#92400E"
        lines = wrap(body, 25)
        for j, ln in enumerate(lines):
            text(x + 31, y + j * 14.5, ln, 10.5, "normal", tcolor)
        y += 14.5 * len(lines) + 8

# ── 下排：版本里程碑 ─────────────────────────────────────────
text(30, 480, "版本里程碑（CHANGELOG 口径，tag 现存 v0.5.0 / v0.5.1 / v0.7.0 / v0.7.1 / v0.11.0 / v0.12.0）", 13, "bold", "#475569")

MILE = [
    ("v0.5", "文档骨架 + 范围锁定", "11 表 / 8 UML 口径定版"),
    ("v0.7", "双通道解析打通", "ASR + OCR 策略接缝"),
    ("v0.7.1", "mock 不冒充转写", "串样例事故修复"),
    ("v0.9", "三层导航模型", "L1 全局 / 面包屑 / tabs"),
    ("v0.10", "时间码芯片", "溯源跳转签名元素"),
    ("v0.11", "ParseMutex 与检索契约", "{total, items} + 上限 200"),
    ("v0.12", "桌面版 sidecar 打包", "长转写分块结构化"),
    ("v0.13", "暗色模式", "渐进渲染 useProgressiveList"),
    ("v0.14", "覆盖提示随物带走", "视图不回显绝对路径"),
    ("v0.15", "长转写实测加固", "锚点确定性 + 抢救截断"),
    ("v0.16", "Mermaid 主题感知", "axe 可达性 0 violation"),
    ("v0.17", "交付迭代（本版）", "文档六章 + 质量门 + Release"),
]

MY, MH, MW, MG = 500, 96, 138, 9
for i, (ver, name, note) in enumerate(MILE):
    x = 30 + i * (MW + MG)
    is_cur = ver == "v0.17"
    accent = "#7C3AED" if is_cur else "#4338CA"
    rect(x, MY, MW, MH, "#F5F3FF" if is_cur else "#FFFFFF", accent, 6, 1.3 if is_cur else 1.1)
    text(x + MW / 2, MY + 26, ver, 14, "bold", accent, "middle")
    for j, ln in enumerate(wrap(name, 11)):
        text(x + MW / 2, MY + 48 + j * 14, ln, 10.5, "bold", "#0F172A", "middle")
    for j, ln in enumerate(wrap(note, 12)):
        text(x + MW / 2, MY + 78 + j * 13, ln, 9.5, "normal", "#475569", "middle")

line([(30, MY - 14), (30 + 12 * (MW + MG) - MG, MY - 14)], stroke="#E2E8F0", sw=2)

# ── 图例与来源 ───────────────────────────────────────────────
LY = 640
rect(30, LY, 1740, 330, "#F8FAFC", "#E2E8F0", 8, 1)
text(46, LY + 30, "读图与口径", 13, "bold", "#475569")
ROWS = [
    ("① 范围", "选题 2026-11-05 已冻结。范围外明确不做：用户注册与权限、上云、并发任务队列、向量语义检索、视频下载、代码沙盒——不实现也不建议。"),
    ("② 解析", "ASR_ENGINE 默认 auto（优先 whisper/yueying，未装重引擎才退 mock）；OCR_ENGINE 可选 rapid|paddle|vision|none。两个引擎均可替换，可用性按实际依赖过滤。"),
    ("③ 结构化", "单条失败只影响该条、批次进 PARTIAL、重试只重跑该条；同一时间仅一个批次在解析（ParseMutex，占用时 409）。长文截断必须诚实上报，不得静默丢内容。"),
    ("④ 证据", "丢失证据链等于破坏项目核心差异化（可信 / 可查 / 可带走）；凡对外导出物（批次 Markdown、/structured 快照）都必须带覆盖提示。"),
    ("⑤ 交付", "文档六章统一落 docs/delivery/；质量门脚本放 tools/ 入库、产物落 output/；Release 由 W6 定版本号后一次性打包，不提前发。"),
]
y = LY + 58
for tag, body in ROWS:
    text(46, y, tag, 11.5, "bold", "#4338CA")
    for j, ln in enumerate(wrap(body, 74)):
        text(120, y + j * 15.5, ln, 11, "normal", "#334155")
    y += 15.5 * len(wrap(body, 74)) + 9

text(
    46,
    LY + 312,
    "同源依据：backend/app/{pipeline,llm,artifacts,export,enums}.py、docs/交付与排期.md §4.2、CHANGELOG.md。识别结果仅供参考。",
    10.5,
    "normal",
    "#64748B",
)

add("</svg>")
Path("docs/figures/svg/fig-aux1-tech-roadmap.svg").write_text("\n".join(out), encoding="utf-8")
print("wrote", len("\n".join(out)), "bytes")
