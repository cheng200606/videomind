"""ER 实体 —— 与 docs/产品定义.md §六 的 9–10 表逐一对应（图 6）。"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel

from app.enums import (
    ArtifactType,
    BatchStatus,
    Channel,
    Confidence,
    RevisionState,
    StageStatus,
    TagTarget,
    VideoStatus,
)


def utcnow() -> datetime:
    # SQLModel 0.0.48 起 datetime 列用 UTCDateTime，naive 值会直接报错，必须带时区
    return datetime.now(timezone.utc)


class VideoBatch(SQLModel, table=True):
    __tablename__ = "video_batch"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=utcnow)
    status: BatchStatus = Field(default=BatchStatus.PENDING)
    video_count: int = 0


class Video(SQLModel, table=True):
    __tablename__ = "video"

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="video_batch.id", index=True)
    path: str
    duration_ms: int = 0
    status: VideoStatus = Field(default=VideoStatus.PENDING)

    # 四阶段状态矩阵；单条重试只重置这几列，不动整批
    transcribe_status: StageStatus = Field(default=StageStatus.PENDING)
    visual_status: StageStatus = Field(default=StageStatus.PENDING)
    structure_status: StageStatus = Field(default=StageStatus.PENDING)
    artifact_status: StageStatus = Field(default=StageStatus.PENDING)
    error: str = ""


class Segment(SQLModel, table=True):
    __tablename__ = "segment"

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    start_ms: int
    end_ms: int
    text: str = Field(sa_column=Column(Text))


class Evidence(SQLModel, table=True):
    """F1 证据链：时间戳 + 原话 + 片段帧 + 通道。"""

    __tablename__ = "evidence"

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    start_ms: int
    end_ms: int
    quote: str = Field(sa_column=Column(Text))
    frame_path: str = ""
    channel: Channel = Channel.ASR


class KnowledgeItem(SQLModel, table=True):
    """可插拔产物的统一载体；两层标签打在 video / item 两级。"""

    __tablename__ = "knowledge_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    type: ArtifactType
    title: str
    content: str = Field(sa_column=Column(Text))
    confidence: Confidence = Confidence.INFERRED
    anchor_ms: int = 0
    evidence_id: Optional[int] = Field(default=None, foreign_key="evidence.id")
    ordinal: int = 0


class Artifact(SQLModel, table=True):
    __tablename__ = "artifact"

    id: Optional[int] = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="knowledge_item.id", index=True)
    schema_type: ArtifactType
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))


class ConflictRecord(SQLModel, table=True):
    """F2 教学一致性校验：冲突是一等数据对象。"""

    __tablename__ = "conflict_record"

    id: Optional[int] = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="knowledge_item.id", index=True)
    source_a: str = ""
    source_b: str = ""
    description: str = Field(sa_column=Column(Text))


class Tag(SQLModel, table=True):
    __tablename__ = "tag"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    suggested_by_ai: bool = False


class TagBinding(SQLModel, table=True):
    __tablename__ = "tag_binding"

    id: Optional[int] = Field(default=None, primary_key=True)
    tag_id: int = Field(foreign_key="tag.id", index=True)
    target_type: TagTarget
    target_id: int


class Note(SQLModel, table=True):
    __tablename__ = "note"

    id: Optional[int] = Field(default=None, primary_key=True)
    # 无登录体系，固定本地用户（范围外：用户注册与权限）
    user_id: str = "local"
    item_id: Optional[int] = Field(default=None, foreign_key="knowledge_item.id")
    content: str = Field(sa_column=Column(Text), default="")
    anchor_ms: int = 0


class Revision(SQLModel, table=True):
    """人在回路：讲义修订留痕 + 状态机（图 7）。"""

    __tablename__ = "revision"

    id: Optional[int] = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="knowledge_item.id", index=True)
    state: RevisionState = RevisionState.DRAFT
    editor: str = "local"
    edited_at: datetime = Field(default_factory=utcnow)
    snapshot: str = Field(sa_column=Column(Text), default="")
