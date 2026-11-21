export type Confidence = 'explicit' | 'inferred' | 'low'
export type ArtifactType = 'summary' | 'uml_draft' | 'key_points' | 'code_blocks'
export type Channel = 'asr' | 'ocr' | 'both'
export type Stage = 'transcribe' | 'visual' | 'structure' | 'artifact'
/** 四阶段状态与后端 app/enums.py 同源；partial=部分成功（分块产物不完整）。 */
export const STAGE_STATUSES = ['pending', 'running', 'done', 'partial', 'failed', 'skipped'] as const
export type StageStatus = (typeof STAGE_STATUSES)[number]
/** 与 backend/app/enums.py 的 VideoStatus / BatchStatus 同源（两者枚举值相同，前端共用一套） */
export const VIDEO_STATUSES = ['pending', 'running', 'succeeded', 'partial', 'failed'] as const
export type VideoStatus = (typeof VIDEO_STATUSES)[number]

/**
 * 终态：批次与视频共用。「全行唯一一份」——视图/Store 里的 `['succeeded','partial','failed']`
 * 一律改从这里判，别再手抄：后端枚举一动，手抄的那几处会静默错（v0.17 P1-2）。
 */
export const TERMINAL_STATUSES = ['succeeded', 'partial', 'failed'] as const

/** 运行态：页面据此禁用删除/重跑，也是筛选器的优先展示顺序 */
export const RUNNING_STATUSES = ['pending', 'running'] as const

/** 筛选器展示顺序：运行态优先，其余按枚举顺序——从上面两份派生，不另抄一遍值 */
export const STATUS_DISPLAY_ORDER: readonly VideoStatus[] = [
  ...RUNNING_STATUSES,
  ...VIDEO_STATUSES.filter((s) => !(RUNNING_STATUSES as readonly string[]).includes(s))
]

/** SSE 的 status 是裸字符串，判终态必须先按枚举收窄 */
export function isTerminalStatus(status: string): boolean {
  return (TERMINAL_STATUSES as readonly string[]).includes(status)
}

export function isRunningStatus(status: string): boolean {
  return (RUNNING_STATUSES as readonly string[]).includes(status)
}
export type RevisionState = 'draft' | 'pending_confirm' | 'confirmed' | 'revised'

export interface Evidence {
  start_ms: number
  end_ms: number
  quote: string
  frame_path: string
  channel: Channel
}

export interface Item {
  id: number
  video_id: number
  video_name: string
  type: ArtifactType
  title: string
  content: string
  confidence: Confidence
  anchor_ms: number
  ordinal: number
  payload: Record<string, unknown>
  evidence: Evidence | null
}

export interface ItemDetail extends Item {
  conflicts: { description: string; source_a: string; source_b: string }[]
  revisions: { id: number; state: RevisionState; editor: string; edited_at: string; snapshot: string }[]
  notes: { id: number; content: string; anchor_ms: number }[]
}

/** 后端不回显本机绝对落盘路径；UI 只用 file_name 与 /media URL（v0.14） */
export interface VideoState {
  id: number
  file_name: string
  media_url: string
  duration_ms: number
  status: VideoStatus
  error: string
  stages: Record<Stage, StageStatus>
}

export interface BatchState {
  id: number
  name: string
  status: VideoStatus
  videos: VideoState[]
}

export interface VideoMeta extends VideoState {
  batch_id: number
}

export interface BatchSummary {
  id: number
  name: string
  status: VideoStatus
  video_count: number
  created_at: string
  /** 按状态计数的视频分布（v0.11），如 { succeeded: 2, failed: 1 } */
  video_status_counts?: Record<string, number>
}

/** v0.11 检索契约：items 最多 200 条（后端上限），total 是未截断的命中总数 */
export interface SearchResponse {
  total: number
  items: Item[]
}

/**
 * 批次结构化快照（GET /api/batches/{id}/structured，v0.14 起每条视频带覆盖提示）。
 * 判定与导出文稿同源：`backend/app/routers/delivery.py` 的 structured()。
 * 前端目前不消费该端点，但契约要跟上，避免外部插件或后续页面接进来时拿到裸数据。
 */
export interface StructuredVideo {
  video_id: number
  file_name: string
  media_url: string
  status: VideoStatus
  duration_ms: number
  item_count: number
  /**
   * 解析覆盖提示：视频终态非「成功」或摘要产物带 notice 时为非空串，多条用「；」连接。
   * 无提示时后端回空串——**不是缺字段**，别用 `?? ''` 之外的假值判断。
   */
  coverage_notice: string
  items: Item[]
}

export interface StructuredBatch {
  batch_id: number
  name: string
  disclaimer: string
  videos: StructuredVideo[]
}

export interface TagInfo {
  id: number
  name: string
  suggested_by_ai: boolean
  bindings: number
  /** 请求带 target 参数时返回：该标签是否绑定在目标上 */
  bound?: boolean
}

export interface StageEvent {
  batch_id: number
  video_id: number | null
  stage: Stage | 'batch'
  status: string
  message: string
  ts: string
  /** 服务端每批单调递增；重连回放时用于去重 */
  seq?: number
}

export interface EngineSettings {
  asr: { current: string; resolved?: string; available: string[] }
  ocr: { current: string; available: string[] }
  output_schemas: string[]
  cache_enabled: boolean
}

export type ModelProvider = 'deepseek' | 'custom'
export type ModelSource = 'saved' | 'env' | 'default'

export interface ModelSettings {
  provider: ModelProvider
  base_url: string
  model: string
  has_key: boolean
  source: ModelSource
}

export interface ModelSettingsInput {
  provider: ModelProvider
  base_url: string
  model: string
  api_key?: string
  clear_api_key?: boolean
}

export interface ModelTestResult {
  ok: boolean
  latency_ms: number
  model: string
  message?: string
  error?: string
}

/** 播放器刻度：一条结论在原片中的位置 */
export interface Mark {
  ms: number
  label: string
  kind?: 'chapter' | 'item' | 'evidence'
}
