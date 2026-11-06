export type Confidence = 'explicit' | 'inferred' | 'low'
export type ArtifactType = 'summary' | 'uml_draft' | 'key_points' | 'code_blocks'
export type Channel = 'asr' | 'ocr' | 'both'
export type Stage = 'transcribe' | 'visual' | 'structure' | 'artifact'
export type StageStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped'
export type VideoStatus = 'pending' | 'running' | 'succeeded' | 'partial' | 'failed'
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

export interface VideoState {
  id: number
  path: string
  file_name?: string
  media_url?: string
  duration_ms: number
  status: VideoStatus
  error: string
  stages: Record<Stage, StageStatus>
}

export interface BatchState {
  id: number
  name: string
  status: string
  videos: VideoState[]
}

export interface VideoMeta extends VideoState {
  batch_id: number
}

export interface BatchSummary {
  id: number
  name: string
  status: string
  video_count: number
  created_at: string
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
