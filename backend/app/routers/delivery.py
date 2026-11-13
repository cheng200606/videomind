"""导出与对外集成（页 9；用例 10「获取批次结构化数据」给插件/外部 Agent 只读快照）。"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from app.db import get_session
from app.enums import BatchStatus
from app.export import build_batch_markdown, coverage_notices
from app.media import display_name, media_url
from app.models import KnowledgeItem, Video, VideoBatch
from app.routers.knowledge import _brief_many

router = APIRouter(prefix="/api", tags=["delivery"])

_TERMINAL = (BatchStatus.SUCCEEDED, BatchStatus.PARTIAL, BatchStatus.FAILED)


def _ensure_terminal(batch: VideoBatch) -> None:
    if batch.status not in _TERMINAL:
        raise HTTPException(409, "批次尚未解析完成，暂不能导出/生成快照")


@router.get("/batches/{batch_id}/export.md")
def export_markdown(batch_id: int, session: Session = Depends(get_session)):
    batch = session.get(VideoBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "批次不存在")
    _ensure_terminal(batch)
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
    _ensure_terminal(batch)
    videos = session.exec(select(Video).where(Video.batch_id == batch_id).order_by(Video.id)).all()
    payload = []
    for video in videos:
        items = session.exec(select(KnowledgeItem).where(
            KnowledgeItem.video_id == video.id).order_by(KnowledgeItem.ordinal)).all()
        payload.append({
            "video_id": video.id,
            "file_name": display_name(video.path, video.batch_id),
            "media_url": media_url(video.path),
            "status": video.status.value,
            "duration_ms": video.duration_ms,
            "item_count": len(items),
            # 与导出文稿同源：外部 Agent 拿到快照也要能看到内容覆盖范围的诚实声明
            "coverage_notice": "；".join(coverage_notices(session, video, items)),
            "items": _brief_many(session, items, video=video),
        })
    return {"batch_id": batch_id, "name": batch.name, "disclaimer": "识别结果仅供参考", "videos": payload}
