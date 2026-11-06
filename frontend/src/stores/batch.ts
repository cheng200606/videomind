import { defineStore } from 'pinia'
import { ref } from 'vue'

import { TERMINAL_BATCH_STATUSES, getBatch, listBatches, openProgress } from '@/api/client'
import type { BatchState, BatchSummary, Stage, StageEvent, StageStatus } from '@/api/types'

export const useBatchStore = defineStore('batch', () => {
  const batches = ref<BatchSummary[]>([])
  const current = ref<BatchState | null>(null)
  const events = ref<StageEvent[]>([])
  const loading = ref(false)
  const error = ref('')
  let close: (() => void) | null = null
  let seq = 0

  async function refreshList() {
    batches.value = await listBatches()
  }

  /** 切换批次/重试后重新打开：先清旧流与旧快照，再拉新快照并订阅 */
  async function open(id: number) {
    stopProgress()
    const mine = ++seq
    loading.value = true
    error.value = ''
    try {
      const snapshot = await getBatch(id)
      if (mine !== seq) return
      current.value = snapshot
      watchProgress(id, mine)
    } catch (err) {
      if (mine !== seq) return
      current.value = null
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  /** SSE 事件只补阶段矩阵；视频/批次终态仍以快照重拉为准 */
  function patchEvent(e: StageEvent) {
    const batch = current.value
    if (!batch || e.batch_id !== batch.id || e.video_id == null) return
    const video = batch.videos.find((v) => v.id === e.video_id)
    if (!video) return
    if (e.stage === 'batch') {
      if (e.status === 'video_start') video.status = 'running'
      return
    }
    if (e.stage in video.stages) {
      video.stages[e.stage as Stage] = e.status as StageStatus
    }
  }

  function watchProgress(id: number, mine: number) {
    close?.()
    events.value = []
    close = openProgress(id, (e) => {
      if (mine !== seq) return
      if (current.value?.id === id) {
        events.value.push(e)
        patchEvent(e)
      }
      if (e.stage === 'batch' && (TERMINAL_BATCH_STATUSES as readonly string[]).includes(e.status)) {
        void getBatch(id).then((b) => {
          if (mine === seq) current.value = b
        })
      }
    })
  }

  function stopProgress() {
    close?.()
    close = null
    seq++
    loading.value = false
    error.value = ''
    current.value = null
    events.value = []
  }

  return { batches, current, events, loading, error, refreshList, open, stopProgress }
})
