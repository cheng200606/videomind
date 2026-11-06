import axios from 'axios'
import type {
  BatchState, BatchSummary, EngineSettings, Item, ItemDetail, ModelSettings, ModelSettingsInput,
  ModelTestResult, RevisionState, SearchResponse, StageEvent, TagInfo, VideoMeta
} from './types'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

/**
 * FastAPI 的 422 detail 是数组；直接 JSON.stringify 会把原始字段名甩给中文用户。
 * 后端 v0.11 起有全局中文处理器，这里对 msg 再做一层兜底中文化，兼容直连旧后端的场景。
 */
const PYDANTIC_MSG_ZH: [RegExp, string][] = [
  [/unable to parse string as an integer|Input should be a valid integer/i, '应为整数'],
  [/Input should be a valid number/i, '应为数字'],
  [/Field required/i, '缺少必填参数'],
  [/should be a valid enumeration/i, '取值不合法'],
  [/String should have at most/i, '超出长度上限'],
]

export function formatDetail(detail: unknown): string {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((entry) => {
      if (typeof entry === 'string') return entry
      if (entry && typeof entry === 'object') {
        const item = entry as { loc?: unknown; msg?: unknown }
        const loc = Array.isArray(item.loc)
          ? item.loc.filter((p) => p !== 'body' && p !== 'query').join('.')
          : ''
        let msg = item.msg == null ? JSON.stringify(entry) : String(item.msg)
        for (const [re, zh] of PYDANTIC_MSG_ZH) {
          if (re.test(msg)) { msg = zh; break }
        }
        return loc ? `${loc}：${msg}` : msg
      }
      return String(entry)
    }).join('；')
  }
  if (typeof detail === 'object' && detail && 'msg' in detail) {
    return String((detail as { msg: unknown }).msg)
  }
  return JSON.stringify(detail)
}

/** 把 FastAPI 的 detail 提到 Error.message 上，前端提示才知道是"状态机拒绝"还是"引擎不可用" */
http.interceptors.response.use(
  (r) => r,
  (error) => {
    const detail = error.response?.data?.detail
    if (detail) error.message = formatDetail(detail)
    return Promise.reject(error)
  }
)

export async function listBatches(): Promise<BatchSummary[]> {
  const { data } = await http.get<BatchSummary[]>('/batches')
  return data
}

export async function createBatch(
  name: string,
  files: File[],
  onProgress?: (percent: number) => void,
  signal?: AbortSignal
): Promise<{ id: number; rejected: { filename: string; reason: string }[] }> {
  const form = new FormData()
  form.append('name', name)
  files.forEach((f) => form.append('files', f))
  const { data } = await http.post<{ id: number; rejected: { filename: string; reason: string }[] }>(
    '/batches', form, {
      // 上传大视频不能套 60s REST 超时；进度只在浏览器给出 total 时更新
      timeout: 0,
      signal,
      onUploadProgress: (e) => {
        if (e.total) onProgress?.(Math.min(100, Math.round((e.loaded / e.total) * 100)))
      }
    })
  return data
}

export async function getBatch(id: number): Promise<BatchState> {
  const { data } = await http.get<BatchState>(`/batches/${id}`)
  return data
}

export async function reparseBatch(id: number): Promise<void> {
  await http.post(`/batches/${id}/parse`)
}

export async function deleteBatch(id: number): Promise<void> {
  await http.delete(`/batches/${id}`)
}

export async function retryVideo(id: number): Promise<void> {
  await http.post(`/videos/${id}/retry`)
}

export async function getVideo(id: number): Promise<VideoMeta> {
  const { data } = await http.get<VideoMeta>(`/videos/${id}`)
  return data
}

/** 上传落盘在 media_root 且经 /media 静态挂载，取文件名即可拼出可播放 URL */
export function mediaUrl(path: string): string {
  return `/media/${path.split(/[\\/]/).pop() ?? ''}`
}

export async function getTranscript(videoId: number): Promise<{ start_ms: number; end_ms: number; text: string }[]> {
  const { data } = await http.get(`/videos/${videoId}/transcript`)
  return data
}

export async function getItems(videoId: number, type?: string): Promise<Item[]> {
  const { data } = await http.get<Item[]>(`/videos/${videoId}/items`, { params: type ? { type } : {} })
  return data
}

export async function getItem(itemId: number): Promise<ItemDetail> {
  const { data } = await http.get<ItemDetail>(`/items/${itemId}`)
  return data
}

export async function addNote(itemId: number, content: string, anchorMs: number): Promise<{ id: number }> {
  const { data } = await http.post<{ id: number }>(`/items/${itemId}/notes`, {
    content, anchor_ms: anchorMs
  })
  return data
}

export async function updateNote(noteId: number, content: string, anchorMs: number): Promise<void> {
  await http.put(`/notes/${noteId}`, { content, anchor_ms: anchorMs })
}

/** state 省略时只追加一版留痕、不跳转状态 */
export async function revise(itemId: number, state?: RevisionState, content = ''): Promise<void> {
  await http.post(`/items/${itemId}/revision`, { state, content, editor: 'local' })
}

/** target 参数：只看某个视频/条目的标签（工作台标签条用 bound 标记渲染） */
export async function listTags(targetType?: 'video' | 'item', targetId?: number): Promise<TagInfo[]> {
  const params = targetType && targetId != null ? { target_type: targetType, target_id: targetId } : {}
  const { data } = await http.get<TagInfo[]>('/tags', { params })
  return data
}

export async function bindTag(name: string, targetType: 'video' | 'item', targetId: number): Promise<void> {
  await http.post('/tags/bind', { name, target_type: targetType, target_id: targetId })
}

export async function dismissTag(tagId: number, targetType: 'video' | 'item', targetId: number): Promise<void> {
  await http.post(`/tags/${tagId}/dismiss`, null, { params: { target_type: targetType, target_id: targetId } })
}

export async function search(params: { tag?: number; q?: string; confidence?: string; video_id?: number }): Promise<SearchResponse> {
  const { data } = await http.get<SearchResponse>('/search', { params })
  return data
}

export async function getEngines(): Promise<EngineSettings> {
  const { data } = await http.get<EngineSettings>('/settings/engines')
  return data
}

export async function setEngines(body: Partial<Record<'asr' | 'ocr' | 'output_schemas', unknown>>): Promise<EngineSettings> {
  const { data } = await http.put<EngineSettings>('/settings/engines', body)
  return data
}

export async function getModelSettings(): Promise<ModelSettings> {
  const { data } = await http.get<ModelSettings>('/settings/model')
  return data
}

export async function setModelSettings(body: ModelSettingsInput): Promise<ModelSettings> {
  const { data } = await http.put<ModelSettings>('/settings/model', body)
  return data
}

export async function testModelSettings(): Promise<ModelTestResult> {
  const { data } = await http.post<ModelTestResult>('/settings/model/test')
  return data
}

/** 批次级 Markdown 文稿直接走浏览器下载，省一份前端拼装逻辑 */
export function exportUrl(batchId: number): string {
  return `/api/batches/${batchId}/export.md`
}

/** 与 stores/batch.ts 共用：终态批次不再订阅 */
export const TERMINAL_BATCH_STATUSES = ['succeeded', 'partial', 'failed'] as const

/** 只有 video_id 为空的 batch 事件才是整批结束；单条视频终态不能关闭整条事件流。 */
export function isBatchTerminalEvent(e: StageEvent): boolean {
  return e.stage === 'batch' && e.video_id == null
    && (TERMINAL_BATCH_STATUSES as readonly string[]).includes(e.status)
}

export interface ProgressHooks {
  onOpen?: () => void
  onError?: () => void
}

export function openProgress(
  batchId: number,
  onEvent: (e: StageEvent) => void,
  hooks: ProgressHooks = {}
): () => void {
  let closed = false
  // video_events=1：新前端需要单条视频终态来实时更新矩阵；默认关闭保证旧前端不会被提前断流
  const source = new EventSource(`/api/batches/${batchId}/progress?video_events=1`)
  source.onopen = () => {
    if (!closed) hooks.onOpen?.()
  }
  source.onerror = () => {
    // 不在这里 close：EventSource 会自动重连；store 同时用快照轮询兜底
    if (!closed) hooks.onError?.()
  }
  source.addEventListener('stage', (ev: MessageEvent) => {
    const e = JSON.parse(ev.data) as StageEvent
    onEvent(e)
    // 服务端推完整批终态就收流；EventSource 默认 ~3s 自动重连，不主动 close 会无限重复收终态
    if (isBatchTerminalEvent(e)) {
      closed = true
      source.close()
    }
  })
  return () => {
    closed = true
    source.close()
  }
}
