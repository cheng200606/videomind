"""`OutputSchemaStrategy` 抽象 + 4 个实现类（类图图 5 的下半部分）。

每个策略 = 一个 Pydantic payload 模型 + 一个从 StructuredDraft 渲染的函数；
新增产物类型不改主链路，只在这里加一个类并注册。
"""

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field

from app.enums import ArtifactType, Channel, Confidence
from app.engines.base import FrameText, KeyFrame, TranscriptSegment
from app.llm import StructuredDraft


@dataclass
class ItemDraft:
    """落库前的统一中间态：KnowledgeItem + 一条 Evidence + 一个 Artifact payload。"""

    type: ArtifactType
    title: str
    content: str
    confidence: Confidence
    anchor_ms: int
    ordinal: int = 0
    quote: str = ""
    channel: Channel = Channel.ASR
    frame_path: str = ""
    payload: dict = field(default_factory=dict)
    conflicts: list[tuple[str, int, int]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class ParseContext:
    draft: StructuredDraft
    segments: list[TranscriptSegment]
    frames: list[KeyFrame]
    ocr: list[FrameText]
    duration_ms: int
    # 解析阶段的诚实提示（如转写超长截断），随摘要产物持久化，前端在工作台展示
    notices: list[str] = field(default_factory=list)


class OutputSchemaStrategy(Protocol):
    atype: ArtifactType
    payload_model: type[BaseModel]

    def build(self, ctx: ParseContext) -> list[ItemDraft]: ...


def _nearest_segment(ctx: ParseContext, ms: int) -> TranscriptSegment | None:
    if not ctx.segments:
        return None
    return min(ctx.segments, key=lambda s: abs(s.start_ms - ms))


def _frame_near(ctx: ParseContext, ms: int) -> str:
    if not ctx.frames:
        return ""
    return min(ctx.frames, key=lambda f: abs(f.ms - ms)).path


def _safe(text: str, limit: int = 40) -> str:
    """mermaid 节点标签里不能出现引号/括号/换行，这里统一洗掉。"""
    cleaned = (text or "").replace("\n", " ")
    for ch in '"[](){}<>|`':
        cleaned = cleaned.replace(ch, "")
    return cleaned.strip()[:limit] or "节点"


# ── payload 契约 ──────────────────────────────────────────────
class SummaryPayload(BaseModel):
    one_line: str
    chapters: list[dict] = Field(default_factory=list)
    # 解析阶段的诚实提示（如「转写超长，仅前 12000 字符参与结构化」），工作台横幅展示
    notice: str = ""


class UmlPayload(BaseModel):
    diagram_type: str
    mermaid: str
    elements: list[dict] = Field(default_factory=list)


class KeyPointsPayload(BaseModel):
    points: list[dict] = Field(default_factory=list)
    pitfalls: list[dict] = Field(default_factory=list)


class CodeBlocksPayload(BaseModel):
    language: str
    blocks: list[dict] = Field(default_factory=list)


# ── 4 个实现 ─────────────────────────────────────────────────
class SummaryStrategy:
    atype = ArtifactType.SUMMARY
    payload_model = SummaryPayload

    def build(self, ctx: ParseContext) -> list[ItemDraft]:
        seg0 = _nearest_segment(ctx, 0)
        chapters = [
            {"title": c.title, "start_ms": c.start_ms, "end_ms": c.end_ms, "gist": c.gist}
            for c in ctx.draft.chapters
        ]
        return [ItemDraft(
            type=self.atype,
            title="内容总结",
            content=ctx.draft.one_line or "（未识别到明确结论）",
            confidence=Confidence.INFERRED,
            anchor_ms=0,
            ordinal=0,
            quote=seg0.text if seg0 else "",
            frame_path=_frame_near(ctx, 0),
            payload=SummaryPayload(one_line=ctx.draft.one_line, chapters=chapters,
                                   notice="；".join(ctx.notices)).model_dump(),
            tags=ctx.draft.tags,
        )]


class UmlDraftStrategy:
    """UML 草稿：让 LLM 的章节/条目渲染成 Mermaid 源码，前端可点元素回证据。

    选 Mermaid 而不是 drawio XML：渲染器 MIT、前端直接渲、导出的 Markdown 在 GitHub 原生可读。
    对不含建模内容的视频，退化为章节流程图——这是输出策略的设计，不是缺陷（产品定义 §九）。
    """

    atype = ArtifactType.UML_DRAFT
    payload_model = UmlPayload

    def build(self, ctx: ParseContext) -> list[ItemDraft]:
        if not ctx.draft.chapters:
            return []
        lines = ["flowchart TD"]
        elements: list[dict] = []
        prev = ""
        for i, ch in enumerate(ctx.draft.chapters, 1):
            node = f"C{i}"
            lines.append(f'{node}["{i}. {_safe(ch.title, 24)}"]')
            elements.append({"id": node, "label": ch.title, "anchor_ms": ch.start_ms, "kind": "chapter"})
            if prev:
                lines.append(f"{prev} --> {node}")
            prev = node
        for j, item in enumerate(ctx.draft.items[:8], 1):
            node = f"K{j}"
            lines.append(f'{node}(["{_safe(item.title, 20)}"])')
            lines.append(f"{prev} -.-> {node}")
            elements.append({"id": node, "label": item.title, "anchor_ms": item.anchor_ms, "kind": "item"})

        first = ctx.draft.chapters[0]
        return [ItemDraft(
            type=self.atype,
            title="UML 草稿 · 章节流程",
            content="\n".join(lines),
            confidence=Confidence.INFERRED,
            anchor_ms=first.start_ms,
            ordinal=1,
            quote=first.gist,
            frame_path=_frame_near(ctx, first.start_ms),
            payload=UmlPayload(diagram_type="flowchart", mermaid="\n".join(lines),
                               elements=elements).model_dump(),
        )]


class KeyPointsStrategy:
    """要点清单 + F3 易错点：pitfall=true 的条目单独成清单。"""

    atype = ArtifactType.KEY_POINTS
    payload_model = KeyPointsPayload

    def build(self, ctx: ParseContext) -> list[ItemDraft]:
        out: list[ItemDraft] = []
        for i, item in enumerate(ctx.draft.items):
            seg = _nearest_segment(ctx, item.anchor_ms)
            out.append(ItemDraft(
                type=self.atype,
                title=item.title,
                content=item.content,
                confidence=item.confidence,
                anchor_ms=item.anchor_ms,
                ordinal=i,
                quote=item.quote or (seg.text if seg else ""),
                channel=Channel.ASR if seg else Channel.BOTH,
                frame_path=_frame_near(ctx, item.anchor_ms),
                payload={"point": item.content, "pitfall": item.pitfall},
                tags=ctx.draft.tags,
            ))
        return out


class CodeBlocksStrategy:
    """代码块：来源是画面通道，channel 标 OCR——证据抽屉里要能看出这是"看到的"不是"听到的"。"""

    atype = ArtifactType.CODE_BLOCKS
    payload_model = CodeBlocksPayload

    def build(self, ctx: ParseContext) -> list[ItemDraft]:
        if not ctx.ocr:
            return []
        blocks: list[dict] = []
        out: list[ItemDraft] = []
        buf: list[str] = []
        buf_ms = 0
        for ft in ctx.ocr:
            if not buf:
                buf_ms = ft.ms
            buf.append(ft.text)
            if len(buf) >= 8:
                blocks.append({"code": "\n".join(buf), "start_ms": buf_ms, "end_ms": ft.ms})
                buf = []
        if buf:
            blocks.append({"code": "\n".join(buf), "start_ms": buf_ms, "end_ms": buf_ms})

        for i, blk in enumerate(blocks[:6]):
            out.append(ItemDraft(
                type=self.atype,
                title=f"代码块 {i + 1}",
                content=blk["code"],
                confidence=Confidence.LOW if i else Confidence.INFERRED,
                anchor_ms=blk["start_ms"],
                ordinal=i,
                quote=blk["code"][:200],
                channel=Channel.OCR,
                frame_path=_frame_near(ctx, blk["start_ms"]),
                payload=CodeBlocksPayload(language=ctx.draft.language, blocks=[blk]).model_dump(),
            ))
        return out


REGISTRY: dict[str, OutputSchemaStrategy] = {
    ArtifactType.SUMMARY.value: SummaryStrategy(),
    ArtifactType.UML_DRAFT.value: UmlDraftStrategy(),
    ArtifactType.KEY_POINTS.value: KeyPointsStrategy(),
    ArtifactType.CODE_BLOCKS.value: CodeBlocksStrategy(),
}


def resolve(names: list[str]) -> list[OutputSchemaStrategy]:
    return [REGISTRY[n] for n in names if n in REGISTRY]
