"""生成 VideoMind 交付文档 Word 骨架（v0.17）。

用法（仓库根目录）：
    <python> tools/make_docx_skeleton.py

产出：docs/delivery/VideoMind_交付文档_v0.17.docx
口径：docs/delivery/排版规范.md（数值改动需同步本脚本与骨架样式表）
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "delivery" / "VideoMind_交付文档_v0.17.docx"

DOC_TITLE = "VideoMind 视析 · 软件工程课程项目交付文档 v0.17"
HEADER_TEXT = "VideoMind 视析 · 软件工程课程项目交付文档 v0.17"

BODY_EAST = "宋体"
HEAD_EAST = "黑体"
CODE_EAST = "Consolas"
WEST = "Times New Roman"

# 章节结构：与 排版规范.md §三 表格逐行对应
CHAPTERS: list[tuple[str, list[str]]] = [
    (
        "第 1 章 项目概述",
        [
            "1.1 引言",
            "1.2 项目背景与痛点",
            "1.3 目标用户与场景",
            "1.4 项目目标与范围",
            "1.5 术语表",
            "1.6 小结",
        ],
    ),
    (
        "第 2 章 可行性分析",
        [
            "2.1 引言",
            "2.2 技术可行性",
            "2.3 经济可行性",
            "2.4 操作可行性",
            "2.5 进度可行性",
            "2.6 风险与对策",
            "2.7 小结",
        ],
    ),
    (
        "第 3 章 需求分析",
        [
            "3.1 引言",
            "3.2 功能需求",
            "3.3 非功能需求",
            "3.4 用例分析",
            "3.5 业务流程",
            "3.6 范围外与诚实边界",
            "3.7 小结",
        ],
    ),
    (
        "第 4 章 系统设计",
        [
            "4.1 引言",
            "4.2 总体架构",
            "4.3 功能模块设计",
            "4.4 数据库设计",
            "4.5 接口设计",
            "4.6 关键流程设计",
            "4.7 界面设计",
            "4.8 小结",
        ],
    ),
    (
        "第 5 章 系统实现与测试",
        [
            "5.1 引言",
            "5.2 开发环境与技术选型",
            "5.3 关键功能实现",
            "5.4 数据库实现（数据字典）",
            "5.5 测试",
            "5.6 迭代与缺陷",
            "5.7 小结",
        ],
    ),
    (
        "第 6 章 附录：小组讨论记录",
        [
            "6.1 记录规则",
            "6.2 轮值分工",
            "6.3 讨论记录",
            "6.4 待办与决议跟踪",
        ],
    ),
]

# 每章「素材来源 / 可插入锚点」，对应 HANDOFF 任务 #4 第 5 条
ANCHORS: dict[str, list[str]] = {
    "第 1 章": [
        "素材：docs/产品定义.md §一、§二、§十一（痛点、画像、差异化话术）",
        "素材：README.md 前两节（一句话定位、目录结构）",
        "插入锚点：1.2 ← 辅 2 痛点对比表（待补）",
        "插入锚点：1.4 ← 辅 1 技术路线图（待补）",
    ],
    "第 2 章": [
        "素材：docs/交付与排期.md §五 七周倒排（进度可行性对照口径）",
        "素材：docs/测试与迭代报告_v0.7/_v0.8/_v0.11/_v0.12.md（技术可行性可核证据）",
        "插入锚点：2.3 ← 辅 4 成本估算表（待补，须体现 F2/F3 各增一次 LLM 调用）",
        "约束：技术可行性每条结论必须挂可核证据，禁用「可支持」「预计」这类无据表述",
    ],
    "第 3 章": [
        "素材：docs/产品定义.md §四（B1–B10 / F1–F5）、§七（10 条用例）、§八（范围外）、§九（诚实边界）",
        "插入锚点：3.4 ← 图 1 用例图（docs/figures/svg/fig1-usecase.svg，已交付）",
        "插入锚点：3.5 ← 图 2 活动图（待补：含知识点 → 卡点判定分支）",
        "插入锚点：3.2 ← 辅 3 多模态 + 多产物示意图（待补）",
    ],
    "第 4 章": [
        "素材：backend/app/pipeline.py（四阶段主链路、ParseMutex、_recompute_batch_status）",
        "素材：backend/app/artifacts.py（OutputSchemaStrategy + 4 个实现）",
        "素材：backend/app/engines/__init__.py（AsrEngine / OcrEngine 注册表）",
        "插入锚点：4.2 ← 图 8 部署图 / 组件图（待补）",
        "插入锚点：4.3 ← 图 5 类图（待补）",
        "插入锚点：4.4 ← 图 6 ER 图（待补，11 表口径）",
        "插入锚点：4.6 ← 图 3 时序图 A、图 4 时序图 B（均待补）",
        "插入锚点：4.6 ← 辅 0 数据流图（docs/figures/svg/fig2-dataflow-context.svg、fig2-dataflow-level1.svg，已交付但降为辅助图）",
        "要求：正文写的行为必须能指到 app/ 下具体文件与函数",
    ],
    "第 5 章": [
        "素材：docs/数据字典.md（C 分支，11 表逐字段，改造为 5.4 一节）",
        "素材：docs/迭代方案_v0.13.md … v0.16.md、补充验证与首屏优化_v0.8.1.md",
        "素材：backend/tests/、frontend/src/__tests__/（测试实跑数字以当日输出为准）",
        "插入锚点：5.1 ← 辅 0 数据流图（如需说明数据走向）",
        "插入锚点：5.3 ← 界面图（docs/prototype/exports/*@2x.png，合入 A 分支后可用）",
        "要求：数据字典与 backend/app/models.py 逐字段一致；图注标注「界面图」",
    ],
    "第 6 章": [
        "素材：本群 W5 起真实讨论轮次归档（由组长提供，落 6.3）",
        "红线：不得补写臆造的既往会议；无记录的周次留空并注明「无记录」",
        "插入锚点：6.3 ← 每次讨论一节（时间、参与人、议题、结论、待办）",
    ],
}


# ---------- 底层工具 ----------

def set_run_font(run, *, east: str = BODY_EAST, west: str = WEST, size: float, bold: bool = False):
    run.font.name = west
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east)


def style_font(style, *, east: str, west: str, size: float, bold: bool = False,
               black: bool = True):
    style.font.name = west
    style.font.size = Pt(size)
    style.font.bold = bold
    if black:
        # Word 内置 Heading 样式自带主题色（accent1 蓝），必须显式压成黑色，
        # 并清掉 themeColor，否则颜色仍会跟主题变
        style.font.color.rgb = RGBColor(0, 0, 0)
        rpr0 = style.element.get_or_add_rPr()
        for color_el in rpr0.findall(qn("w:color")):
            rpr0.remove(color_el)
        color_el = OxmlElement("w:color")
        color_el.set(qn("w:val"), "000000")
        rpr0.append(color_el)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rfonts.get(qn(attr)) is not None:
            del rfonts.attrib[qn(attr)]
    rfonts.set(qn("w:ascii"), west)
    rfonts.set(qn("w:hAnsi"), west)
    rfonts.set(qn("w:eastAsia"), east)


def add_field(paragraph, instr: str, placeholder: str = "（按 F9 更新）"):
    """插入一个 Word 域（TOC / 页码）。"""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    run._r.append(begin)

    run2 = paragraph.add_run()
    instr_el = OxmlElement("w:instrText")
    instr_el.set(qn("xml:space"), "preserve")
    instr_el.text = f" {instr} "
    run2._r.append(instr_el)

    run3 = paragraph.add_run()
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    run3._r.append(sep)

    run4 = paragraph.add_run(placeholder)

    run5 = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run5._r.append(end)

    for r in (run, run2, run3, run4, run5):
        set_run_font(r, size=10.5)
    return paragraph


def set_page_numbering(section, *, fmt: str, start: int | None = None):
    sect_pr = section._sectPr
    for old in sect_pr.findall(qn("w:pgNumType")):
        sect_pr.remove(old)
    el = OxmlElement("w:pgNumType")
    el.set(qn("w:fmt"), fmt)
    if start is not None:
        el.set(qn("w:start"), str(start))
    sect_pr.insert_element_before(
        el,
        "w:cols",
        "w:formProt",
        "w:vAlign",
        "w:noEndnote",
        "w:titlePg",
        "w:textDirection",
        "w:bidi",
        "w:rtlGutter",
        "w:docGrid",
        "w:printerSettings",
        "w:sectPrChange",
    )


def config_section(section, *, margins=True):
    if margins:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3.0)
        section.right_margin = Cm(2.5)
        section.header_distance = Cm(1.5)
        section.footer_distance = Cm(1.75)


def add_footer_page_number(section):
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_field(p, "PAGE", "1")


def add_header(section):
    header = section.header
    header.is_linked_to_previous = False
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.line_spacing = Pt(16)    # 固定行高：文字上留出空间给下边框线
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(HEADER_TEXT)
    set_run_font(run, size=9)
    # 页眉下 0.5pt 细线，画在段落「下边框」上；space 为线到文字的间距（磅）
    pPr = p._p.get_or_add_pPr()
    for old in pPr.findall(qn("w:pBdr")):
        pPr.remove(old)
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "6")
    bottom.set(qn("w:color"), "000000")
    borders.append(bottom)
    pPr.insert_element_before(
        borders,
        "w:shd",
        "w:tabs",
        "w:suppressAutoHyphens",
        "w:kinsoku",
        "w:wordWrap",
        "w:overflowPunct",
        "w:topLinePunct",
        "w:autoSpaceDE",
        "w:autoSpaceDN",
        "w:bidi",
        "w:adjustRightInd",
        "w:snapToGrid",
        "w:spacing",
        "w:ind",
        "w:contextualSpacing",
        "w:mirrorIndents",
        "w:suppressOverlap",
        "w:jc",
        "w:textDirection",
        "w:textAlignment",
        "w:textboxTightWrap",
        "w:outlineLvl",
        "w:divId",
        "w:cnfStyle",
        "w:rPr",
        "w:sectPr",
        "w:pPrChange",
    )


def clear_header_footer(section):
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    for part in (section.header, section.footer):
        for p in part.paragraphs:
            for r in list(p.runs):
                r._r.getparent().remove(r._r)


def _paint(run, hex_color: str):
    color = OxmlElement("w:color")
    color.set(qn("w:val"), hex_color)
    run._element.rPr.append(color)


def add_pending(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(0)
    run = p.add_run(f"【{text}】")
    set_run_font(run, east="楷体", size=12)
    _paint(run, "808080")
    return p


def add_anchor(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(0)
    run = p.add_run(f"※ {text}")
    set_run_font(run, east="楷体", size=10.5)
    _paint(run, "1F4E79")
    return p


def style_three_line(table, *, header_rows: int = 1):
    """三线表：顶线 1.5pt、栏目线 0.75pt、底线 1.5pt、其余无框线。

    注意 OOXML 对 tblPr / tcPr 的子元素顺序有硬要求，顺序错了边框会被 Word 忽略，
    所以这里一律用 insert_element_before 按 schema 顺序插入，不用 append。
    """
    tbl = table._tbl
    tblPr = tbl.tblPr

    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "auto")
        borders.append(el)
    tblPr.insert_element_before(
        borders,
        "w:shd",
        "w:tblLayout",
        "w:tblCellMar",
        "w:tblLook",
        "w:tblCaption",
        "w:tblDescription",
    )

    def set_edge(cell, edge, sz):
        tcPr = cell._tc.get_or_add_tcPr()
        tcBorders = tcPr.find(qn("w:tcBorders"))
        if tcBorders is None:
            tcBorders = OxmlElement("w:tcBorders")
            tcPr.insert_element_before(
                tcBorders,
                "w:shd",
                "w:noWrap",
                "w:tcMar",
                "w:textDirection",
                "w:tcFitText",
                "w:vAlign",
                "w:hideMark",
            )
        for old in tcBorders.findall(qn(f"w:{edge}")):
            tcBorders.remove(old)
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        # tcBorders 内部的边顺序：top, left, bottom, right, insideH, insideV, tl2br, tr2bl
        order = ["w:top", "w:left", "w:bottom", "w:right",
                 "w:insideH", "w:insideV", "w:tl2br", "w:tr2bl"]
        idx = order.index(f"w:{edge}") + 1
        later = order[idx:]
        pos = len(tcBorders)
        for i, child in enumerate(list(tcBorders)):
            tag = child.tag
            if any(tag == qn(t) for t in later):
                pos = i
                break
        tcBorders.insert(pos, el)

    rows = table.rows
    for ci in range(len(table.columns)):
        set_edge(rows[0].cells[ci], "top", 12)          # 1.5pt = 12 eighth-points
        set_edge(rows[-1].cells[ci], "bottom", 12)
        for hi in range(header_rows):
            set_edge(rows[hi].cells[ci], "bottom", 6)   # 0.75pt

    table.alignment = WD_TABLE_ALIGNMENT.CENTER


# ---------- 文档构建 ----------

def build():
    doc = Document()

    # --- 全局样式 ---
    normal = doc.styles["Normal"]
    style_font(normal, east=BODY_EAST, west=WEST, size=12)
    pf = normal.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.first_line_indent = Pt(24)

    specs = {
        "Heading 1": dict(east=HEAD_EAST, west=WEST, size=16, bold=True,
                          align=WD_ALIGN_PARAGRAPH.CENTER, before=24, after=18, page_break=True),
        "Heading 2": dict(east=HEAD_EAST, west=WEST, size=14, bold=True,
                          align=WD_ALIGN_PARAGRAPH.LEFT, before=12, after=6, page_break=False),
        "Heading 3": dict(east=HEAD_EAST, west=WEST, size=12, bold=True,
                          align=WD_ALIGN_PARAGRAPH.LEFT, before=6, after=3, page_break=False),
    }
    for name, s in specs.items():
        st = doc.styles[name]
        style_font(st, east=s["east"], west=s["west"], size=s["size"], bold=s["bold"])
        p = st.paragraph_format
        p.alignment = s["align"]
        p.space_before = Pt(s["before"])
        p.space_after = Pt(s["after"])
        p.line_spacing = 1.5
        p.first_line_indent = Pt(0)
        p.keep_with_next = True
        if s["page_break"]:
            p.page_break_before = True
        st.element.get_or_add_pPr()
        # 黑体标题在 Word 里不应被主题字体覆盖
        rpr = st.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:eastAsia"), s["east"])

    cap = doc.styles["Caption"]
    style_font(cap, east=BODY_EAST, west=WEST, size=10.5)
    cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(3)
    cap.paragraph_format.space_after = Pt(6)
    cap.paragraph_format.line_spacing = 1.0
    cap.paragraph_format.first_line_indent = Pt(0)

    # --- 第 1 节：封面 ---
    sec = doc.sections[0]
    config_section(sec)
    clear_header_footer(sec)

    for _ in range(4):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Pt(0)
    set_run_font(p.add_run("软件工程课程项目"), east=BODY_EAST, size=16)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(24)
    p.paragraph_format.space_after = Pt(24)
    p.paragraph_format.first_line_indent = Pt(0)
    set_run_font(p.add_run("VideoMind 视析"), east=HEAD_EAST, size=42, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Pt(0)
    set_run_font(p.add_run("可溯源的教学视频知识库系统"), east=HEAD_EAST, size=28, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.first_line_indent = Pt(0)
    set_run_font(p.add_run("软件工程课程项目 · 需求与设计文档 v0.17"), east=BODY_EAST, size=16)

    for _ in range(2):
        doc.add_paragraph()

    info = doc.add_table(rows=5, cols=2)
    info.autofit = False
    info_rows = [
        ("组　　号", "（待填）"),
        ("小组成员", "（待填：姓名 / 学号，共 4 人）"),
        ("角色分工", "需求与统筹 / 原型与界面 / UML 与建模 / 后端与数据"),
        ("指导教师", "（待填）"),
        ("完成日期", "2026 年 12 月"),
    ]
    col_w = (Cm(3.6), Cm(11.4))          # 合计 15.0 cm，正文区 15.5 cm 内
    for i, (k, v) in enumerate(info_rows):
        c0, c1 = info.rows[i].cells
        for cell, txt, bold, w in ((c0, k, True, col_w[0]), (c1, v, False, col_w[1])):
            cell.width = w
            para = cell.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.first_line_indent = Pt(0)
            para.paragraph_format.line_spacing = 1.0
            para.paragraph_format.space_before = Pt(2)
            para.paragraph_format.space_after = Pt(2)
            set_run_font(para.add_run(txt), size=10.5, bold=bold)
    # 固定布局 + 同步 tblGrid，Word 才会按上面的列宽渲染（否则按内容自适应）
    for ci, w in enumerate(col_w):
        info.columns[ci].width = w
        for cell in info.columns[ci].cells:
            cell.width = w
    tblPr = info._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.insert_element_before(
        layout, "w:tblCellMar", "w:tblLook", "w:tblCaption", "w:tblDescription"
    )
    style_three_line(info)

    # --- 第 2 节：目录（罗马数字页码）---
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    config_section(sec)
    clear_header_footer(sec)
    set_page_numbering(sec, fmt="upperRoman", start=1)
    add_footer_page_number(sec)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(18)
    p.paragraph_format.first_line_indent = Pt(0)
    set_run_font(p.add_run("目　录"), east=HEAD_EAST, size=16, bold=True)

    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.line_spacing = 1.5
    add_field(p, 'TOC \\o "1-3" \\h \\z \\u', "（按 F9 生成目录）")

    # --- 第 3 节：图表目录 ---
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    config_section(sec)
    clear_header_footer(sec)
    set_page_numbering(sec, fmt="upperRoman")           # 续罗马数字
    add_footer_page_number(sec)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(18)
    p.paragraph_format.first_line_indent = Pt(0)
    set_run_font(p.add_run("图表目录"), east=HEAD_EAST, size=16, bold=True)

    for label, instr in (
        ("一、插图目录", 'TOC \\h \\z \\c "图"'),
        ("二、表格目录", 'TOC \\h \\z \\c "表"'),
    ):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.first_line_indent = Pt(0)
        set_run_font(p.add_run(label), east=HEAD_EAST, size=14, bold=True)

        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(0)
        add_field(p, instr, "（题注建好后按 F9 生成）")

    # --- 第 4 节：正文（阿拉伯数字，从 1 起）---
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    config_section(sec)
    clear_header_footer(sec)
    set_page_numbering(sec, fmt="decimal", start=1)
    add_header(sec)
    add_footer_page_number(sec)

    first_chapter = True
    for title, sections in CHAPTERS:
        h = doc.add_heading(title, level=1)
        if first_chapter:
            h.paragraph_format.page_break_before = False   # 本章紧跟分节符，不需要再加分页
            first_chapter = False

        chapter_no = title.split()[1]                      # "1" / "2" …
        for line in ANCHORS.get(f"第 {chapter_no} 章", []):
            add_anchor(doc, line)

        for sec_title in sections:
            doc.add_heading(sec_title, level=2)
            add_pending(doc, "待补：本节正文")
            doc.add_paragraph()

        add_pending(doc, "本章数据与结论以下列来源为准，落笔前请复核")

    # 结尾说明：不进目录，故用普通段落而非 Heading 1
    doc.add_page_break()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(24)
    p.paragraph_format.space_after = Pt(18)
    p.paragraph_format.first_line_indent = Pt(0)
    set_run_font(p.add_run("骨架使用说明（本页提交前删除）"), east=HEAD_EAST, size=16, bold=True)

    for line in [
        "本骨架只给结构与样式，不含任何未经核实的事实性正文；【待补】处必须由责任人按素材来源填写。",
        "已交付素材在每章开头以「※ 素材 / 插入锚点」列出，便于 W6 逐章粘贴。",
        "图注、表注必须先转成 Word「题注」（引用 → 插入题注），图表目录才能自动生成。",
        "所有 TOC、页码、图表目录均为域：定稿前按 Ctrl+A 再 F9 →「更新整个目录」。",
        "排版数值见 docs/delivery/排版规范.md；改样式请同时改 tools/make_docx_skeleton.py，保证可重建。",
    ]:
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(0)
        set_run_font(p.add_run("· " + line), size=12)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"saved: {path}")
    print(f"size: {path.stat().st_size} bytes")
    sys.exit(0)
