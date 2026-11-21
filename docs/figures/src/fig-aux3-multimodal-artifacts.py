#!/usr/bin/env python
"""辅图 3 · 多模态 + 多产物示意图（建议置于 ch4 系统设计）

左：两条输入通道（音频 ASR / 画面 OCR），两个可插拔接缝；
中：llm.structure 结构化 + ParseContext 上下文；
右：经 OutputSchemaStrategy 插拔点产出四类产物，给出注册方式与视图落点。

口径与代码同源：backend/app/artifacts.py（ItemDraft / ParseContext /
OutputSchemaStrategy / REGISTRY / resolve / 四个 Payload）、backend/app/enums.py。
「识别结果仅供参考」为红线要求文案。

重新生成（在仓库根目录执行）：
    python docs/figures/src/fig-aux3-multimodal-artifacts.py
产物：docs/figures/svg/fig-aux3-multimodal-artifacts.svg（按 LF 写入，勿手改 SVG）
"""
from pathlib import Path
from html import escape

W, H = 1800, 850
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


def panel(x, y, w, h, title):
    rect(x, y, w, h, "#F8FAFC", "#E2E8F0", 8, 1)
    text(x + 16, y + 26, title, 13, "bold", "#475569")


def card(x, y, w, h, title, rows, accent="#4338CA", title_size=13.5):
    soft = "#EEF2FF" if accent == "#4338CA" else "#F5F3FF"
    rect(x, y, w, h, "#FFFFFF", accent, 6, 1.2)
    add(
        f'<path d="M{x + 6},{y} h{w - 12} a6,6 0 0 1 6,6 v28 h-{w} v-28 '
        f'a6,6 0 0 1 6,-6 z" fill="{soft}"/>'
    )
    line([(x, y + 34), (x + w, y + 34)], stroke=accent)
    text(x + w / 2, y + 23, title, title_size, "bold", "#0F172A", "middle")
    for i, s in enumerate(rows):
        text(x + 12, y + 54 + i * 17, s, 11, "normal", "#334155")


def note_box(x, y, w, h, title, rows, fill="#FFFBEB", stroke="#F59E0B", ink="#92400E"):
    rect(x, y, w, h, fill, stroke, 6, 1.1)
    text(x + 14, y + 24, title, 12, "bold", ink)
    for i, s in enumerate(rows):
        text(x + 14, y + 46 + i * 17, s, 10.5, "normal", ink)


add(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}" font-family="{FONT}">'
)
add(
    '''<defs>
<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
 orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" fill="none" stroke="#64748B"
 stroke-width="1.2"/></marker>
<marker id="tri" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="10" markerHeight="10"
 orient="auto-start-reverse"><path d="M1,1 L11,6 L1,11 z" fill="#FFFFFF" stroke="#7C3AED"
 stroke-width="1.1"/></marker>
</defs>'''
)
rect(0, 0, W, H, "#FFFFFF", "#FFFFFF")

text(30, 40, "辅图 3 · 多模态双通道解析与四类可插拔产物", 18, "bold", "#0F172A")
text(
    30,
    64,
    "每条产物携带 Evidence（时间戳 + 原话 + 片段帧 + 通道）；产物类型由 OutputSchemaStrategy 插拔点决定，新增产物不改主链路。",
    11,
    "normal",
    "#64748B",
)

# ═══ 面板一：输入通道 ═══════════════════════════════════════
panel(30, 92, 430, 570, "输入通道（两个可插拔接缝）")

card(
    48, 132, 394, 118, "AsrEngine · 音频通道",
    ["+ name : str   + isAvailable() : bool",
     "+ transcribe(path) : AsrResult",
     "实现：MockAsr / WhisperAsr /",
     "        YueyingAsr / FunASR"],
)
text(48, 272, "开关 ASR_ENGINE（默认 auto）", 10.5, "normal", "#475569")

card(
    48, 292, 394, 136, "OcrEngine · 画面通道",
    ["+ name : str",
     "+ recognize(frames) : FrameText[]",
     "实现：RapidOcr / PaddleOcr /",
     "        VisionModelOcr",
     "可用性按实际依赖过滤"],
)
text(48, 452, "开关 OCR_ENGINE（rapid|paddle|vision|none）", 10.5, "normal", "#475569")

note_box(
    48, 474, 394, 104, "前置：抽帧与去重",
    ["ffmpeg 按固定间隔抽帧 → media/{batch}_{file}/",
     "frames.file_thumbnail + abs_diff 均值差去重",
     "SIMILAR_THRESHOLD 与 ocr.dedupe_frames 同源",
     "读图失败只保留该帧并记 warning，不静默"],
)

text(48, 604, "失败隔离：单条失败只影响该条，批次进 PARTIAL；重试只重跑该条。", 10.5, "normal", "#475569")
text(48, 628, "同一时刻仅一个批次在解析（ParseMutex，占用时 409）。", 10.5, "normal", "#475569")
text(48, 652, "mock 只回放同名内置样例，绝不冒充转写。", 10.5, "normal", "#92400E")

# ═══ 面板二：结构化 ═════════════════════════════════════════
panel(480, 92, 370, 570, "结构化（LLM，单次或分块）")

card(
    498, 132, 334, 136, "llm.structure()",
    ["入参 segments + ocr + duration_ms",
     "出参 StructuredDraft",
     "      .chapters / .items / .language",
     "      .report（截断等诚实提示）",
     "分块输入时间归零，只出相对毫秒"],
)

note_box(
    498, 280, 334, 110, "分块与合并（长转写）",
    ["按段边界切块，逐块调用后合并",
     "_rebase_draft 按块起点回移并夹取锚点",
     "个别块失败 → 阶段 PARTIAL（不静默丢）",
     "解析疑似截断先 _salvage_truncated"],
    fill="#F5F3FF", stroke="#7C3AED", ink="#5B21B6",
)

card(
    498, 404, 334, 136, "ParseContext",
    ["draft : StructuredDraft",
     "segments : TranscriptSegment[]",
     "frames : KeyFrame[]   ocr : FrameText[]",
     "duration_ms : int",
     "notices : str[]（诚实提示随产物落库）"],
)

note_box(
    498, 552, 334, 88, "无 Key / 调用失败",
    ["降级为规则草稿（fallback_draft），",
     "report.fallback = True 并写入 notice。",
     "不得当成模型效果演示。"],
)

# ═══ 面板三：输出产物 ═══════════════════════════════════════
panel(870, 92, 900, 570, "输出产物（build(ctx) 按 OutputSchemaStrategy 插拔点产出）")

ARTI = [
    ("SummaryStrategy",
     ["atype = SUMMARY", "payload = SummaryPayload",
      "one_line / chapters", "notice：截断提示随产物带走"], "#4338CA"),
    ("UmlDraftStrategy",
     ["atype = UML_DRAFT", "payload = UmlPayload",
      "diagram_type / mermaid", "elements；标签经 _safe 洗字符"], "#4338CA"),
    ("KeyPointsStrategy",
     ["atype = KEY_POINTS", "payload = KeyPointsPayload",
      "points / pitfalls", "卡点即 pitfalls，可跳回原片"], "#4338CA"),
    ("CodeBlocksStrategy",
     ["atype = CODE_BLOCKS", "payload = CodeBlocksPayload",
      "language / blocks", "仅画面通道触发，channel=OCR"], "#7C3AED"),
]
AW, AH, AGAP = 204, 118, 10
for i, (name, rows, accent) in enumerate(ARTI):
    x = 888 + i * (AW + AGAP)
    card(x, 132, AW, AH, name, rows, accent, 12.5)

rect(888, 272, 846, 92, "#FFFFFF", "#4338CA", 6, 1.2)
text(902, 296, "插拔点契约（backend/app/artifacts.py · OutputSchemaStrategy）", 12, "bold", "#3730A3")
text(902, 318, "class OutputSchemaStrategy(Protocol):", 11, "normal", "#0F172A")
text(910, 338, "atype : ArtifactType      payload_model : type[BaseModel]", 11, "normal", "#334155")
text(910, 356, "build(self, ctx: ParseContext) -> list[ItemDraft]", 11, "normal", "#334155")

rect(888, 380, 846, 92, "#EEF2FF", "#4338CA", 6, 1.1)
text(902, 404, "注册与解析（artifacts.py · REGISTRY / resolve）", 12, "bold", "#3730A3")
for i, s in enumerate([
    "REGISTRY: dict[str, OutputSchemaStrategy] = {summary, uml_draft, key_points, code_blocks}",
    "resolve(names) -> list[OutputSchemaStrategy]：按需装配本次要跑的产物集合",
    "新增产物类型 = 新策略类 + 注册一行，parse_video 主链路不动",
]):
    text(902, 426 + i * 18, s, 10.8, "normal", "#3730A3")

text(888, 502, "落库与视图落点", 11.5, "bold", "#334155")
MAPS = [
    ("SUMMARY", "工作台摘要 + 章节大纲；notice 驱动截断横幅"),
    ("UML_DRAFT", "MermaidView 渲染（主题变量随暗色切换）"),
    ("KEY_POINTS", "知识点区 + pitfalls 卡点，时间码可跳回原片"),
    ("CODE_BLOCKS", "代码块视图；缺失类型如实为空，不以规则文本冒充"),
]
for i, (k, v) in enumerate(MAPS):
    text(888, 526 + i * 20, k, 10.5, "bold", "#4338CA")
    text(982, 526 + i * 20, "→  " + v, 10.5, "normal", "#475569")

text(888, 620, "一条产物 = KnowledgeItem + 一条 Evidence + 一个 Artifact payload；", 10.5, "normal", "#475569")
text(888, 640, "Artifact.item_id → KnowledgeItem.id，schema_type 取该策略的 atype。", 10.5, "normal", "#475569")

# 四张卡 → 契约框（实现关系）
for i in range(4):
    cx = 888 + i * (AW + AGAP) + AW / 2
    line([(cx, 250), (cx, 270)], dash="5 4", marker_end="tri")

# ═══ 连线 ═══════════════════════════════════════════════════
line([(442, 191), (470, 191), (470, 200), (498, 200)], marker_end="arrow")
line([(442, 360), (470, 360), (470, 472), (498, 472)], marker_end="arrow")
line([(832, 472), (860, 472), (860, 318), (886, 318)], marker_end="arrow")

# ═══ 底部图例 ═══════════════════════════════════════════════
LY = 682
rect(30, LY, 1740, 140, "#F8FAFC", "#E2E8F0", 8, 1)
text(46, LY + 28, "读图与口径", 13, "bold", "#475569")
ROWS = [
    "① 双通道各自可替换：换引擎只改实现类与注册表，parse_video 主链路不动；通道不可用时该阶段记 SKIPPED，视频仍可 SUCCEEDED。",
    "② 四类产物是同一插拔点的四个实现，不是四段硬编码；证据链在 ItemDraft 阶段已绑定（channel 区分 asr / ocr / both）。",
    "③ 代码块当前由画面通道产出：ctx.ocr 为空则返回空列表，需 OCR_ENGINE=rapid 且视频确有画面文字；缺失时如实为空。",
]
for i, r in enumerate(ROWS):
    text(46, LY + 54 + i * 22, r, 11, "normal", "#334155")
text(
    46,
    LY + 128,
    "识别结果仅供参考。同源依据：backend/app/artifacts.py、engines/、llm.py、enums.py。",
    10.5,
    "normal",
    "#64748B",
)

add("</svg>")
Path("docs/figures/svg/fig-aux3-multimodal-artifacts.svg").write_text("\n".join(out), encoding="utf-8")
print("wrote", len("\n".join(out)), "bytes")
