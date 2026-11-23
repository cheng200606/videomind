from enum import Enum


class Stage(str, Enum):
    """批次进度页的「四阶段 × N 视频」矩阵列（docs/交付与排期.md 页 3）。"""

    TRANSCRIBE = "transcribe"   # ① 音频通道：ASR 转写
    VISUAL = "visual"           # ② 画面通道：关键帧 + OCR
    STRUCTURE = "structure"     # LLM 结构化
    ARTIFACT = "artifact"       # 产物生成与落库


STAGES: tuple[Stage, ...] = (Stage.TRANSCRIBE, Stage.VISUAL, Stage.STRUCTURE, Stage.ARTIFACT)


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    PARTIAL = "partial"   # 阶段部分成功：如分块结构化个别块失败，产物可用但不完整
    FAILED = "failed"
    SKIPPED = "skipped"   # 无字幕降级 / OCR 关闭时走这里（页 12 异常态）


class VideoStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"   # 批次部分成功——单条失败不重跑整批的前提
    FAILED = "failed"


class BatchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class Channel(str, Enum):
    """Evidence.channel：结论出自哪一路。"""

    ASR = "asr"
    OCR = "ocr"
    BOTH = "both"


class Confidence(str, Enum):
    """F4 不确定性分级：明述 / 推断 / 低置信。"""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    LOW = "low"


class ArtifactType(str, Enum):
    SUMMARY = "summary"
    UML_DRAFT = "uml_draft"
    KEY_POINTS = "key_points"
    CODE_BLOCKS = "code_blocks"


class TagTarget(str, Enum):
    VIDEO = "video"
    ITEM = "item"


class RevisionState(str, Enum):
    """讲义状态机（图 7 右半）。"""

    DRAFT = "draft"
    PENDING_CONFIRM = "pending_confirm"
    CONFIRMED = "confirmed"
    REVISED = "revised"


REVISION_TRANSITIONS: dict[RevisionState, tuple[RevisionState, ...]] = {
    RevisionState.DRAFT: (RevisionState.PENDING_CONFIRM,),
    RevisionState.PENDING_CONFIRM: (RevisionState.CONFIRMED, RevisionState.DRAFT),
    RevisionState.CONFIRMED: (RevisionState.REVISED, RevisionState.DRAFT),
    RevisionState.REVISED: (RevisionState.PENDING_CONFIRM,),
}
