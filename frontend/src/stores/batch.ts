import { defineStore } from 'pinia'
import { ref } from 'vue'

import { TERMINAL_BATCH_STATUSES, getBatch, listBatches, openProgress } from '@/api/client'
import type { BatchState, BatchSummary, Stage, StageEvent, StageStatus, VideoStatus } from '@/api/types'

const TERMINAL_VIDEO_STATUSES: VideoStatus[] = ['succeeded', 'partial', 'failed']

function isTerminalStatus(status: string): boolean {
  return (TERMINAL_BATCH_STATUSES as readonly string[]).includes(status)
}

function isBatchTerminalEvent(e: StageEvent): boolean {
  // 单条视频终态也是 stage=batch；必须用 video_id 为空区分整批结束
  return e.stage === 'batch' && e.video_id == null && isTerminalStatus(e.status)
}

export const useBatchStore = defineStore('batch', () => {
  const batches = ref<BatchSummary[]>([])
  const current = ref<BatchState | null>(null)
  const events = ref<StageEvent[]>([])
  const loading = ref(false)
  const error = ref('')
  const connectionLost = ref(false)

  let close: (() => void) | null = null
  let seq = 0
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let seen = new Set<string>()

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

  /** 事件只补矩阵；单条终态直接落状态，整批终态才重拉快照 */
  function patchEvent(e: StageEvent) {
    const batch = current.value
    if (!batch || e.batch_id !== batch.id || e.video_id == null) return
    const video = batch.videos.find((v) => v.id === e.video_id)
    if (!video) return
    if (e.stage === 'batch') {
      if (e.status === 'video_start') {
        video.status = 'running'
        video.error = ''
        for (const stage of Object.keys(video.stages) as Stage[]) video.stages[stage] = 'pending'
      } else if (TERMINAL_VIDEO_STATUSES.includes(e.status as VideoStatus)) {
        video.status = e.status as VideoStatus
        if (e.status === 'failed' && e.message) video.error = e.message
      }
      return
    }
    if (e.stage in video.stages) {
      video.stages[e.stage as Stage] = e.status as StageStatus
    }
  }

  /** 重连会回放历史；按完整事件去重，进程重启后 seq 归零也不会误吞新事件 */
  function remember(e: StageEvent): boolean {
    const key = JSON.stringify(e)
    if (seen.has(key)) return false
    seen.add(key)
    if (seen.size > 1000) seen = new Set<string>()
    return true
  }

  function pushEvent(e: StageEvent) {
    events.value.push(e)
    if (events.value.length > 200) events.value.splice(0, events.value.length - 200)
  }

  function stopPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function startPolling(id: number, mine: number) {
    if (pollTimer !== null) return
    // SSE 断线兜底：后端崩溃/网络切换时仍能把批次推进到终态，而不是永远“解析中”
    pollTimer = setInterval(() => {
      void (async () => {
        try {
          const snapshot = await getBatch(id)
          if (mine !== seq) return
          current.value = snapshot
          if (isTerminalStatus(snapshot.status)) {
            stopPolling()
            connectionLost.value = false
          }
        } catch {
          // 后端仍未恢复：保留最后一份快照，横幅继续提示
        }
      })()
    }, 4000)
  }

  function watchProgress(id: number, mine: number) {
    close?.()
    stopPolling()
    events.value = []
    seen = new Set<string>()
    connectionLost.value = false
    close = openProgress(id, (e) => {
      if (mine !== seq) return
      if (current.value?.id !== id) return
      if (!remember(e)) return
      pushEvent(e)
      patchEvent(e)
      if (isBatchTerminalEvent(e)) {
        stopPolling()
        connectionLost.value = false
        void getBatch(id).then((b) => {
          if (mine === seq) current.value = b
        })
      }
    }, {
      onOpen: () => {
        if (mine !== seq) return
        connectionLost.value = false
        stopPolling()
      },
      onError: () => {
        if (mine !== seq) return
        connectionLost.value = true
        startPolling(id, mine)
      }
    })
  }

  function stopProgress() {
    close?.()
    close = null
    stopPolling()
    seq++
    loading.value = false
    error.value = ''
    connectionLost.value = false
    current.value = null
    events.value = []
    seen = new Set<string>()
  }

  return {
    batches, current, events, loading, error, connectionLost,
    refreshList, open, stopProgress
  }
})
