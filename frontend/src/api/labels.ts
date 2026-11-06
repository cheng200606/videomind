/**
 * 枚举原值 → 中文展示的唯一出口：所有页面共用，杜绝 succeeded / pending_confirm 直接上 UI。
 * 后端枚举见 backend/app/enums.py，两边改名要同步。
 */

export type TagType = 'success' | 'warning' | 'danger' | 'info' | 'primary'

/** 批次/视频共用一套状态枚举值（BatchStatus、VideoStatus） */
export const STATUS_LABEL: Record<string, string> = {
  pending: '等待',
  running: '解析中',
  succeeded: '成功',
  partial: '部分成功',
  failed: '失败'
}

export const STATUS_TYPE: Record<string, TagType> = {
  pending: 'info',
  running: 'primary',
  succeeded: 'success',
  partial: 'warning',
  failed: 'danger'
}

/** 四阶段矩阵的列头（进度页表格按它 v-for，别把事件流专用的 key 混进来） */
export const STAGE_LABEL: Record<string, string> = {
  transcribe: '① ASR 转写',
  visual: '② 画面 OCR',
  structure: '③ LLM 结构化',
  artifact: '④ 产物落库'
}

/** 事件流的 stage：比矩阵多「批次」级事件与单条开跑事件 */
export const EVENT_STAGE_LABEL: Record<string, string> = {
  ...STAGE_LABEL,
  batch: '批次',
  video_start: '开始解析'
}

export const STAGE_STATUS_LABEL: Record<string, string> = {
  pending: '等待',
  running: '进行中',
  done: '完成',
  failed: '失败',
  skipped: '降级跳过',
  succeeded: '成功',
  partial: '部分成功',
  video_start: '开始解析',
  video_failed: '单条失败'
}

export const STAGE_STATUS_TYPE: Record<string, TagType> = {
  pending: 'info',
  running: 'primary',
  done: 'success',
  failed: 'danger',
  skipped: 'warning',
  succeeded: 'success',
  partial: 'warning',
  video_failed: 'danger'
}

export const ARTIFACT_LABEL: Record<string, string> = {
  summary: '内容总结',
  key_points: '知识要点',
  uml_draft: 'UML 草稿',
  code_blocks: '代码块'
}

/** F4 不确定性分级：产物与检索结果共用 */
export const CONFIDENCE_LABEL: Record<string, string> = {
  explicit: '明述',
  inferred: '推断',
  low: '低置信'
}

export const CONFIDENCE_TYPE: Record<string, TagType> = {
  explicit: 'success',
  inferred: 'warning',
  low: 'danger'
}

export const REVISION_LABEL: Record<string, string> = {
  draft: '草稿',
  pending_confirm: '待确认',
  confirmed: '已确认',
  revised: '已修订'
}

export const REVISION_TYPE: Record<string, TagType> = {
  draft: 'info',
  pending_confirm: 'warning',
  confirmed: 'success',
  revised: 'primary'
}

export const EDITOR_LABEL: Record<string, string> = {
  local: '本地用户'
}

/** ASR 引擎展示名；mock 必须显式写明“不读取视频”，避免真实视频被样例冒充 */
export const ASR_LABEL: Record<string, string> = {
  auto: '自动（优先本地真实引擎）',
  whisper: 'Whisper 本地转写',
  yueying: 'yueying 转写',
  funasr: 'FunASR 转写',
  mock: '演示样例（不读取视频）'
}

export const OCR_LABEL: Record<string, string> = {
  none: '关闭',
  rapid: 'RapidOCR',
  paddle: 'PaddleOCR',
  vision: '视觉模型'
}

export const MODEL_PROVIDER_LABEL: Record<string, string> = {
  deepseek: 'DeepSeek',
  custom: '自定义模型'
}

/** 讲义状态机（图 7 右半，与 backend/app/enums.py 的 REVISION_TRANSITIONS 同源） */
export const REVISION_TRANSITIONS: Record<string, string[]> = {
  draft: ['pending_confirm'],
  pending_confirm: ['confirmed', 'draft'],
  confirmed: ['revised', 'draft'],
  revised: ['pending_confirm']
}

/** 后端时间戳均为带时区的 UTC ISO；展示统一转本地 */
export function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}

export function fmtDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

/** 毫秒 → m:ss；超过 1 小时进位成 h:mm:ss，避免出现 75:30 这类读不懂的分秒 */
export function clock(ms: number): string {
  const total = Math.floor(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = String(total % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

/** 时间轴位置百分比：clamp 到 0–100，duration 为 0 时不把刻度甩出轨道 */
export function pct(ms: number, total: number): number {
  if (!Number.isFinite(total) || total <= 0) return 0
  return Math.min(100, Math.max(0, (ms / total) * 100))
}
