import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getBatch, listBatches, openProgress } from '@/api/client'
import { STAGE_STATUSES, isRunningStatus, isTerminalStatus } from '@/api/types'
import type { BatchState, BatchSummary, Stage, StageEvent, VideoStatus } from '@/api/types'

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

  /**
   * 事件只补矩阵；单条终态直接落状态，整批终态才重拉快照。
   *
   * 批次级事件（video_id 为空）走单独一条路径：后端 parse_batch 一开跑就推
   * `batch/running`，收尾推终态。这两条都得更新批次头，否则解析期间批次头会
   * 一直停在快照里的「等待」，直到终态重拉才跳变（v0.17 修）。
   * 注意不能并进下面的单条路径——那里紧接着按 video_id 查 videos，批次级事件
   * 会查不到而再次 return，等于没改。
   */
  function patchEvent(e: StageEvent) {
    const batch = current.value
    if (!batch || e.batch_id !== batch.id) return

    if (e.video_id == null) {
      // 只认后端 VideoStatus 枚举内的值：SSE 的 status 是裸字符串，别把脏值写进批次头
      if (isTerminalStatus(e.status) || isRunningStatus(e.status)) {
        batch.status = e.status as VideoStatus
      }
      return
    }

    const video = batch.videos.find((v) => v.id === e.video_id)
    if (!video) return
    if (e.stage === 'batch') {
      if (e.status === 'video_start') {
        video.status = 'running'
        video.error = ''
        for (const stage of Object.keys(video.stages) as Stage[]) video.stages[stage] = 'pending'
      } else if (isTerminalStatus(e.status)) {
        video.status = e.status as VideoStatus
        if (e.status === 'failed' && e.message) video.error = e.message
      }
      return
    }
    if (e.stage in video.stages) {
      // SSE 的 status 是裸字符串：先按后端枚举收窄，非法值不写进阶段矩阵
      const status = STAGE_STATUSES.find((s) => s === e.status)
      if (status) video.stages[e.stage as Stage] = status
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
