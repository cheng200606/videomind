import { defineStore } from 'pinia'
import { ref } from 'vue'

import { TERMINAL_BATCH_STATUSES, getBatch, listBatches, openProgress } from '@/api/client'
import type { BatchState, BatchSummary, StageEvent } from '@/api/types'

export const useBatchStore = defineStore('batch', () => {
  const batches = ref<BatchSummary[]>([])
  const current = ref<BatchState | null>(null)
  const events = ref<StageEvent[]>([])
  let close: (() => void) | null = null

  async function refreshList() {
    batches.value = await listBatches()
  }

  async function open(id: number) {
    current.value = await getBatch(id)
    watchProgress(id)
  }

  /** 批次进度页靠 SSE 推，不做轮询；进程重启事件即失效，重新打开页面会拉一次快照 */
  function watchProgress(id: number) {
    close?.()
    events.value = []
    close = openProgress(id, (e) => {
      events.value.push(e)
      if (e.stage === 'batch' && (TERMINAL_BATCH_STATUSES as readonly string[]).includes(e.status)) {
        void getBatch(id).then((b) => { current.value = b })
      }
    })
  }

  function stopProgress() {
    close?.()
    close = null
  }

  return { batches, current, events, refreshList, open, stopProgress }
})
