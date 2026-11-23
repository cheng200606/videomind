"""条目 / 证据 / 标签 / 检索 / 笔记 / 修订（页 4、5、6、7、8）。"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlmodel import Session, or_, select

from app.db import get_session
from app.enums import REVISION_TRANSITIONS, ArtifactType, Confidence, RevisionState, TagTarget
from app.media import display_name
from app.models import (
    Artifact,
    ConflictRecord,
    Evidence,
    KnowledgeItem,
    Note,
    Revision,
    Tag,
    TagBinding,
    Video,
)

router = APIRouter(prefix="/api", tags=["knowledge"])

_SEARCH_LIMIT = 200
_IN_CLAUSE_CHUNK = 400   # SQLite 变量数上限约 999，IN 分块避免超限


class NoteIn(BaseModel):
    content: str = ""
    anchor_ms: int = 0


class RevisionIn(BaseModel):
    state: RevisionState | None = None
    editor: str = "local"
    content: str = ""


def _video_of(session: Session, item: KnowledgeItem) -> Video:
    return session.get(Video, item.video_id)


def _brief(session: Session, item: KnowledgeItem, video: Video | None = None,
           ev: Evidence | None = None, art: Artifact | None = None) -> dict:
    """条目摘要。调用方批量场景可传入预取的 video/evidence/artifact，避免逐条 N+1。"""
    if video is None:
        video = _video_of(session, item)
    if ev is None and item.evidence_id:
        ev = session.get(Evidence, item.evidence_id)
    if art is None:
        art = session.exec(select(Artifact).where(Artifact.item_id == item.id)).first()
    return {
        "id": item.id,
        "video_id": item.video_id,
        "video_name": display_name(video.path, video.batch_id) if video else "",
        "type": item.type.value,
        "title": item.title,
        "content": item.content,
        "confidence": item.confidence.value,
        "anchor_ms": item.anchor_ms,
        "ordinal": item.ordinal,
        "payload": art.payload if art else {},
        "evidence": {
            "start_ms": ev.start_ms, "end_ms": ev.end_ms, "quote": ev.quote,
            "frame_path": ev.frame_path, "channel": ev.channel.value,
        } if ev else None,
    }


def _preload_brief_maps(session: Session, items: list[KnowledgeItem], video: Video | None = None):
    """为一批条目一次性取齐 Evidence 与 Artifact（chunked IN），消除逐条 3 查询的 N+1。"""
    evidence_ids = [i.evidence_id for i in items if i.evidence_id]
    evidences: dict[int, Evidence] = {}
    for start in range(0, len(evidence_ids), _IN_CLAUSE_CHUNK):
        chunk = evidence_ids[start:start + _IN_CLAUSE_CHUNK]
        for ev in session.exec(select(Evidence).where(Evidence.id.in_(chunk))).all():
            evidences[ev.id] = ev
    item_ids = [i.id for i in items]
    artifacts: dict[int, Artifact] = {}
    for start in range(0, len(item_ids), _IN_CLAUSE_CHUNK):
        chunk = item_ids[start:start + _IN_CLAUSE_CHUNK]
        for art in session.exec(select(Artifact).where(Artifact.item_id.in_(chunk))).all():
            artifacts[art.item_id] = art
    videos: dict[int, Video] = {}
    if video is None:
        video_ids = list({i.video_id for i in items})
        for start in range(0, len(video_ids), _IN_CLAUSE_CHUNK):
            chunk = video_ids[start:start + _IN_CLAUSE_CHUNK]
            for v in session.exec(select(Video).where(Video.id.in_(chunk))).all():
                videos[v.id] = v
    return video, evidences, artifacts, videos


def _brief_many(session: Session, items: list[KnowledgeItem], video: Video | None = None) -> list[dict]:
    video, evidences, artifacts, videos = _preload_brief_maps(session, items, video)
    return [_brief(session, i,
                   video=video or videos.get(i.video_id),
                   ev=evidences.get(i.evidence_id or 0),
                   art=artifacts.get(i.id)) for i in items]


@router.get("/videos/{video_id}/items")
def video_items(video_id: int, item_type: ArtifactType | None = Query(None, alias="type"),
                session: Session = Depends(get_session)):
    if session.get(Video, video_id) is None:
        raise HTTPException(404, "视频不存在")
    stmt = select(KnowledgeItem).where(KnowledgeItem.video_id == video_id)
    if item_type is not None:
        stmt = stmt.where(KnowledgeItem.type == item_type)
    items = session.exec(stmt.order_by(KnowledgeItem.ordinal)).all()
    return _brief_many(session, items, video=session.get(Video, video_id))


@router.get("/items/{item_id}")
def item_detail(item_id: int, session: Session = Depends(get_session)):
    item = session.get(KnowledgeItem, item_id)
    if item is None:
        raise HTTPException(404, "条目不存在")
    data = _brief(session, item)
    data["conflicts"] = [
        {"description": c.description, "source_a": c.source_a, "source_b": c.source_b}
        for c in session.exec(select(ConflictRecord).where(ConflictRecord.item_id == item_id)).all()
    ]
    data["revisions"] = [
        {"id": r.id, "state": r.state.value, "editor": r.editor,
         "edited_at": r.edited_at, "snapshot": r.snapshot}
        for r in session.exec(select(Revision).where(Revision.item_id == item_id)
                              .order_by(Revision.id)).all()
    ]
    data["notes"] = [
        {"id": n.id, "content": n.content, "anchor_ms": n.anchor_ms}
        for n in session.exec(select(Note).where(Note.item_id == item_id).order_by(Note.id)).all()
    ]
    return data


@router.post("/items/{item_id}/notes", status_code=201)
def add_note(item_id: int, body: NoteIn, session: Session = Depends(get_session)):
    item = session.get(KnowledgeItem, item_id)
    if item is None:
        raise HTTPException(404, "条目不存在")
    note = Note(item_id=item.id, content=body.content, anchor_ms=body.anchor_ms or item.anchor_ms)
    session.add(note)
    session.commit()
    session.refresh(note)
    return {"id": note.id, "anchor_ms": note.anchor_ms}


@router.put("/notes/{note_id}")
def edit_note(note_id: int, body: NoteIn, session: Session = Depends(get_session)):
    note = session.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "笔记不存在")
    note.content = body.content
    note.anchor_ms = body.anchor_ms or note.anchor_ms
    session.add(note)
    session.commit()
    return {"ok": True}


@router.post("/items/{item_id}/revision")
def revise(item_id: int, body: RevisionIn, session: Session = Depends(get_session)):
    """讲义修订留痕：状态机草稿→待确认→已确认→已修订（图 7），非法跳转直接拒。"""
    item = session.get(KnowledgeItem, item_id)
    if item is None:
        raise HTTPException(404, "条目不存在")
    latest = session.exec(select(Revision).where(Revision.item_id == item_id)
                          .order_by(Revision.id.desc())).first()
    current = latest.state if latest else RevisionState.DRAFT
    if body.state is not None and body.state not in REVISION_TRANSITIONS[current]:
        raise HTTPException(422, f"不允许的状态跳转：{current.value} → {body.state.value}")
    target = body.state or current
    if body.state is None and not body.content:
        raise HTTPException(422, "无可留痕的变更：要么给 state 跳状态，要么给 content 改内容")

    if body.content:
        item.content = body.content
        session.add(item)
    session.add(Revision(item_id=item_id, state=target, editor=body.editor,
                         snapshot=body.content or item.content))
    session.commit()
    return {"state": target.value}


@router.get("/tags")
def list_tags(target_type: TagTarget | None = Query(None), target_id: int | None = Query(None),
              session: Session = Depends(get_session)):
    """标签清单；带 target 参数时附加 bound 标记，工作台用它渲染当前视频/条目的标签条。"""
    # 一次取全部绑定按 tag 分组，替代逐标签查询的 N+1
    all_bindings = session.exec(select(TagBinding)).all()
    by_tag: dict[int, list[TagBinding]] = {}
    for b in all_bindings:
        by_tag.setdefault(b.tag_id, []).append(b)
    out = []
    for t in session.exec(select(Tag)).all():
        bindings = by_tag.get(t.id, [])
        bound = (target_type is not None and target_id is not None
                 and any(b.target_type == target_type and b.target_id == target_id for b in bindings))
        out.append({"id": t.id, "name": t.name, "suggested_by_ai": t.suggested_by_ai,
                    "bindings": len(bindings), "bound": bound})
    return out


class TagBindIn(BaseModel):
    name: str
    target_type: TagTarget
    target_id: int


@router.post("/tags/bind", status_code=201)
def bind_tag(body: TagBindIn, session: Session = Depends(get_session)):
    """人工绑定标签。对 AI 已建议的绑定再绑一次视为「采纳」，标签转为人工确认。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "标签名不能为空")
    tag = session.exec(select(Tag).where(Tag.name == name)).first()
    if tag is None:
        tag = Tag(name=name, suggested_by_ai=False)   # 人工新建的标签不算 AI 建议
        session.add(tag)
        session.commit()
        session.refresh(tag)
    exists = session.exec(select(TagBinding).where(
        TagBinding.tag_id == tag.id, TagBinding.target_type == body.target_type,
        TagBinding.target_id == body.target_id)).first()
    if exists is None:
        session.add(TagBinding(tag_id=tag.id, target_type=body.target_type, target_id=body.target_id))
    elif tag.suggested_by_ai:
        tag.suggested_by_ai = False   # 采纳：AI 建议经人工确认，不再以「建议」身份示人
        session.add(tag)
    session.commit()
    return {"id": tag.id}


@router.post("/tags/{tag_id}/dismiss")
def dismiss_ai_tag(tag_id: int, target_type: TagTarget, target_id: int, session: Session = Depends(get_session)):
    """驳回 AI 标签建议（人机协同：采纳/驳回都是显式动作）。"""
    rows = session.exec(select(TagBinding).where(
        TagBinding.tag_id == tag_id, TagBinding.target_type == target_type,
        TagBinding.target_id == target_id)).all()
    for r in rows:
        session.delete(r)
    tag = session.get(Tag, tag_id)
    if tag:
        tag.suggested_by_ai = False
        session.add(tag)
    session.commit()
    return {"ok": True}


@router.get("/search")
def search(tag: int | None = None, q: str | None = None, confidence: str | None = None,
           video_id: int | None = None, session: Session = Depends(get_session)):
    """跨视频条目检索：标签过滤 + 关键词 + 置信度，不是语义检索（产品定义 §九 诚实边界）。

    空条件直接返回全库会让「检索」退化成「浏览」，还随数据量线性变慢——必须给至少
    一个条件；命中数按 LIMIT 截断并返回 total，前端提示缩小范围。
    """
    if not tag and not (q and q.strip()) and not confidence and not video_id:
        raise HTTPException(422, "至少提供一个检索条件：标签 / 关键词 / 置信度")
    conds = []
    if video_id:
        conds.append(KnowledgeItem.video_id == video_id)
    if q and q.strip():
        # LIKE 通配符按字面匹配：用户搜 "100%" 不该命中任意以 100 结尾的文本
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        conds.append(or_(KnowledgeItem.title.like(like, escape="\\"),
                         KnowledgeItem.content.like(like, escape="\\")))
    if confidence:
        try:
            level = Confidence(confidence)
        except ValueError:
            raise HTTPException(422, "未知置信度，可选 explicit / inferred / low")
        conds.append(KnowledgeItem.confidence == level)
    if tag:
        item_ids = [b.target_id for b in session.exec(select(TagBinding).where(
            TagBinding.tag_id == tag, TagBinding.target_type == TagTarget.ITEM)).all()]
        video_ids = [b.target_id for b in session.exec(select(TagBinding).where(
            TagBinding.tag_id == tag, TagBinding.target_type == TagTarget.VIDEO)).all()]
        # 视频级标签作用于该视频当前全部条目（重跑新增条目自动继承），条目级只命中自身
        if not item_ids and not video_ids:
            return {"total": 0, "items": []}
        conditions = []
        if item_ids:
            conditions.append(KnowledgeItem.id.in_(item_ids))
        if video_ids:
            conditions.append(KnowledgeItem.video_id.in_(video_ids))
        conds.append(or_(*conditions))

    base = select(KnowledgeItem).where(*conds)
    total = session.exec(select(func.count()).select_from(KnowledgeItem).where(*conds)).one()
    if q and q.strip():
        # 相关度排序（v0.13）：标题命中 ×3 > 内容命中 ×1，双命中叠加；同分按视频与时间锚点稳定序。
        # 在 SQL 里算 rank 保持单查询；仍是标签过滤而非语义检索，排序只反映字面命中强度。
        rank = (case((KnowledgeItem.title.like(like, escape="\\"), 3), else_=0)
                + case((KnowledgeItem.content.like(like, escape="\\"), 1), else_=0))
        order = (rank.desc(), KnowledgeItem.video_id, KnowledgeItem.anchor_ms)
    else:
        order = (KnowledgeItem.video_id, KnowledgeItem.anchor_ms)
    items = session.exec(base.order_by(*order).limit(_SEARCH_LIMIT)).all()
    return {"total": total, "items": _brief_many(session, items)}
