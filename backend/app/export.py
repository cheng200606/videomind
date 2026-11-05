"""批次级 Markdown 导出（页 9 / 用例「导出批次文稿」）。

产物含 UML 草稿（mermaid）、总结、要点、代码块与逐条溯源；导出物在 GitHub 上可直接渲染。
"""

from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from app.enums import ArtifactType, Confidence, RevisionState, TagTarget, VideoStatus
from app.models import Artifact, ConflictRecord, Evidence, KnowledgeItem, Note, Revision, Tag, TagBinding, Video, VideoBatch

# 导出文稿面向中文读者：枚举原值（succeeded / explicit / confirmed…）一律映射成中文
_VIDEO_STATUS = {
    VideoStatus.PENDING: "等待", VideoStatus.RUNNING: "解析中", VideoStatus.SUCCEEDED: "成功",
    VideoStatus.PARTIAL: "部分成功", VideoStatus.FAILED: "失败",
}
_CONFIDENCE = {
    Confidence.EXPLICIT: "明述", Confidence.INFERRED: "推断", Confidence.LOW: "低置信",
}
_REVISION = {
    RevisionState.DRAFT: "草稿", RevisionState.PENDING_CONFIRM: "待确认",
    RevisionState.CONFIRMED: "已确认", RevisionState.REVISED: "已修订",
}


def ts(ms: int) -> str:
    total = int(ms // 1000)
    return f"{total // 60}:{total % 60:02d}"


def _tag_names(session: Session, target_type: TagTarget, target_id: int) -> list[str]:
    rows = session.exec(select(TagBinding).where(
        TagBinding.target_type == target_type, TagBinding.target_id == target_id)).all()
    names = []
    for r in rows:
        tag = session.get(Tag, r.tag_id)
        if tag:
            names.append(tag.name)
    return names


def _evidence_line(session: Session, item: KnowledgeItem) -> str:
    if not item.evidence_id:
        return ""
    ev = session.get(Evidence, item.evidence_id)
    if ev is None:
        return ""
    quote = (ev.quote or "").replace("\n", " ")[:80]
    where = "画面" if ev.channel.value == "ocr" else ("语音+画面" if ev.channel.value == "both" else "语音")
    return f"> 证据 `[{ts(ev.start_ms)}]` · {where} · 「{quote}」 · 识别结果仅供参考"


def build_batch_markdown(session: Session, batch_id: int) -> str:
    batch = session.get(VideoBatch, batch_id)
    if batch is None:
        raise KeyError(f"批次 {batch_id} 不存在")

    videos = session.exec(select(Video).where(Video.batch_id == batch.id)).all()
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    out: list[str] = [
        f"# {batch.name} · 视频知识结构化文稿",
        "",
        f"> 由 VideoMind 视析 生成 · {now} · 共 {len(videos)} 条视频",
        "> 所有结论均由 ASR / OCR + 大模型识别产出，**识别结果仅供参考**，请以原片为准。",
        "",
        "## 批次概览",
        "",
        "| 视频 | 时长 | 状态 | 标签 |",
        "| --- | --- | --- | --- |",
    ]
    for v in videos:
        tags = "、".join(_tag_names(session, TagTarget.VIDEO, v.id)) or "-"
        out.append(f"| `{Path(v.path).name}` | {ts(v.duration_ms)} | {_VIDEO_STATUS[v.status]} | {tags} |")
    out.append("")

    for v in videos:
        items = session.exec(select(KnowledgeItem).where(
            KnowledgeItem.video_id == v.id).order_by(KnowledgeItem.ordinal)).all()
        out += ["---", "", f"## {Path(v.path).name}", ""]

        summary = next((i for i in items if i.type == ArtifactType.SUMMARY), None)
        if summary:
            payload = _payload(session, summary)
            out += [f"**一句话结论**：{summary.content}", ""]
            chapters = payload.get("chapters", [])
            if chapters:
                out.append("**章节大纲**")
                out.append("")
                for c in chapters:
                    out.append(f"- `[{ts(c['start_ms'])}]` {c['title']} — {c.get('gist', '')}")
                out.append("")

        uml = next((i for i in items if i.type == ArtifactType.UML_DRAFT), None)
        if uml:
            out += ["**结构草稿（Mermaid）**", "", "```mermaid", uml.content, "```", ""]

        points = [i for i in items if i.type == ArtifactType.KEY_POINTS]
        if points:
            pitfalls = [i for i in points if _payload(session, i).get("pitfall")]
            out += ["**知识要点**", ""]
            for i in points:
                line = f"- `[{ts(i.anchor_ms)}]` {i.content}（{_CONFIDENCE[i.confidence]}）"
                if i in pitfalls:
                    line = f"- ⚠ `[{ts(i.anchor_ms)}]` {i.content}（讲师强调/纠错处）"
                out.append(line)
                ev = _evidence_line(session, i)
                if ev:
                    out.append(ev)
            out.append("")

        codes = [i for i in items if i.type == ArtifactType.CODE_BLOCKS]
        for i in codes:
            lang = _payload(session, i).get("language", "text")
            out += [f"**{i.title}** `[{ts(i.anchor_ms)}]`", "", f"```{lang}", i.content, "```", ""]
            ev = _evidence_line(session, i)
            if ev:
                out += [ev, ""]

        conflicts = session.exec(select(ConflictRecord).where(
            ConflictRecord.item_id.in_([i.id for i in items] or [-1]))).all() if items else []
        if conflicts:
            out += ["**前后不一致提示（F2）**", ""]
            for c in conflicts:
                out.append(f"- {c.description}（{c.source_a} ↔ {c.source_b}）")
            out.append("")

        notes = session.exec(select(Note).where(Note.item_id.in_([i.id for i in items] or [-1]))).all() if items else []
        if notes:
            out += ["**批注**", ""]
            for n in notes:
                out.append(f"- `[{ts(n.anchor_ms)}]` {n.content}")
            out.append("")

        revisions = session.exec(select(Revision).where(Revision.item_id.in_([i.id for i in items] or [-1]))).all() if items else []
        confirmed = [r for r in revisions if r.state in (RevisionState.CONFIRMED, RevisionState.REVISED)]
        if confirmed:
            out += ["**版本记录**", ""]
            for r in confirmed:
                item = session.get(KnowledgeItem, r.item_id)
                title = item.title if item else f"条目 #{r.item_id}"
                out.append(f"- {r.edited_at:%Y-%m-%d %H:%M} · {r.editor} · {title} · {_REVISION[r.state]}")
            out.append("")

    return "\n".join(out)


def _payload(session: Session, item: KnowledgeItem) -> dict:
    art = session.exec(select(Artifact).where(Artifact.item_id == item.id)).first()
    return art.payload if art else {}
