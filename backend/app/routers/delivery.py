"""导出与对外集成（页 9；用例 10「获取批次结构化数据」给插件/外部 Agent 只读快照）。"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from app.db import get_session
from app.export import build_batch_markdown
from app.models import KnowledgeItem, Video, VideoBatch
from app.routers.knowledge import _brief

router = APIRouter(prefix="/api", tags=["delivery"])


@router.get("/batches/{batch_id}/export.md")
def export_markdown(batch_id: int, session: Session = Depends(get_session)):
    batch = session.get(VideoBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "批次不存在")
    md = build_batch_markdown(session, batch_id)
    filename = quote(f"{batch.name}.md")
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/batches/{batch_id}/structured")
def structured(batch_id: int, session: Session = Depends(get_session)):
    batch = session.get(VideoBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "批次不存在")
    videos = session.exec(select(Video).where(Video.batch_id == batch_id)).all()
    payload = []
    for video in videos:
        items = session.exec(select(KnowledgeItem).where(
            KnowledgeItem.video_id == video.id).order_by(KnowledgeItem.ordinal)).all()
        payload.append({
            "video_id": video.id,
            "path": video.path,
            "duration_ms": video.duration_ms,
            "items": [_brief(session, i) for i in items],
        })
    return {"batch_id": batch_id, "name": batch.name, "disclaimer": "识别结果仅供参考", "videos": payload}
