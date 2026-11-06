import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { StageEvent } from '@/api/types'

const mocks = vi.hoisted(() => ({
  getBatch: vi.fn(),
  openProgress: vi.fn()
}))

vi.mock('@/api/client', () => ({
  getBatch: mocks.getBatch,
  listBatches: vi.fn(),
  openProgress: mocks.openProgress,
  // store 里判终态用的常量，mock 必须同步导出
  TERMINAL_BATCH_STATUSES: ['succeeded', 'partial', 'failed']
}))

import { useBatchStore } from '@/stores/batch'

function event(status: string): StageEvent {
  return { batch_id: 1, video_id: null, stage: 'batch', status, message: '', ts: '2026-11-06T00:00:00+00:00' }
}

function stageEvent(overrides: Partial<StageEvent> = {}): StageEvent {
  return {
    batch_id: 1, video_id: 10, stage: 'transcribe', status: 'done', message: '',
    ts: '2026-11-06T00:00:00+00:00', ...overrides
  } as StageEvent
}

function videoTerminal(status = 'succeeded', overrides: Partial<StageEvent> = {}): StageEvent {
  return {
    batch_id: 1, video_id: 10, stage: 'batch', status, message: 'demo.mp4',
    ts: '2026-11-06T00:00:01+00:00', seq: 8, ...overrides
  } as StageEvent
}

function snapshot(status = 'running') {
  return {
    id: 1, name: 'X', status,
    videos: [{
      id: 10, path: 'C:\\data\\1_demo.mp4', file_name: 'demo.mp4', duration_ms: 1000,
      status: 'running', error: '', stages: {
        transcribe: 'pending', visual: 'pending', structure: 'pending', artifact: 'pending'
      }
    }]
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('批次进度 store', () => {
  it('open 先拉快照，再订阅 SSE', async () => {
    const store = useBatchStore()
    mocks.getBatch.mockResolvedValue({ id: 1, name: 'X', status: 'running', videos: [] })
    mocks.openProgress.mockReturnValue(() => {})

    await store.open(1)

    expect(mocks.getBatch).toHaveBeenCalledWith(1)
    expect(mocks.openProgress).toHaveBeenCalledWith(1, expect.any(Function), expect.any(Object))
    expect(store.current?.status).toBe('running')
  })

  it('收到终态事件后重拉快照（SSE 事件不落库，快照是唯一事实来源）', async () => {
    const store = useBatchStore()
    // 用对象持有回调：TS 会把「闭包内赋值的 let 变量」窄化成 null，直接 ?.() 调用报 never
    const holder: { cb?: (e: StageEvent) => void } = {}
    mocks.getBatch.mockImplementation(async () => ({ id: 1, name: 'X', status: 'succeeded', videos: [] }))
    mocks.openProgress.mockImplementation((_id: number, cb: (e: StageEvent) => void) => {
      holder.cb = cb
      return () => {}
    })

    await store.open(1)
    holder.cb?.(event('succeeded'))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(mocks.getBatch).toHaveBeenCalledTimes(2)
    expect(store.current?.status).toBe('succeeded')
  })

  it('进行中事件不触发快照刷新', async () => {
    const store = useBatchStore()
    const holder: { cb?: (e: StageEvent) => void } = {}
    mocks.getBatch.mockResolvedValue({ id: 1, name: 'X', status: 'running', videos: [] })
    mocks.openProgress.mockImplementation((_id: number, cb: (e: StageEvent) => void) => {
      holder.cb = cb
      return () => {}
    })

    await store.open(1)
    holder.cb?.(event('running'))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(mocks.getBatch).toHaveBeenCalledTimes(1)
  })

  it('阶段事件即时更新矩阵，video_start 把视频置 running', async () => {
    const store = useBatchStore()
    const holder: { cb?: (e: StageEvent) => void } = {}
    mocks.getBatch.mockResolvedValue(snapshot())
    mocks.openProgress.mockImplementation((_id: number, cb: (e: StageEvent) => void) => {
      holder.cb = cb
      return () => {}
    })

    await store.open(1)
    holder.cb?.(stageEvent({ stage: 'batch', status: 'video_start' }))
    holder.cb?.(stageEvent({ stage: 'transcribe', status: 'done' }))

    expect(store.current?.videos[0].stages.transcribe).toBe('done')
    expect(store.current?.videos[0].status).toBe('running')
    expect(store.events).toHaveLength(2)
  })

  it('单条视频终态直接更新该条状态，不重拉整批快照', async () => {
    const store = useBatchStore()
    const holder: { cb?: (e: StageEvent) => void } = {}
    mocks.getBatch.mockResolvedValue(snapshot())
    mocks.openProgress.mockImplementation((_id: number, cb: (e: StageEvent) => void) => {
      holder.cb = cb
      return () => {}
    })

    await store.open(1)
    holder.cb?.(videoTerminal('partial'))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(store.current?.videos[0].status).toBe('partial')
    expect(mocks.getBatch).toHaveBeenCalledTimes(1)
    expect(store.events).toHaveLength(1)
  })

  it('只有 video_id 为空的整批终态才重拉快照；重复回放事件按 seq 去重', async () => {
    const store = useBatchStore()
    const holder: { cb?: (e: StageEvent) => void } = {}
    mocks.getBatch.mockImplementation(async () => ({ id: 1, name: 'X', status: 'succeeded', videos: [] }))
    mocks.openProgress.mockImplementation((_id: number, cb: (e: StageEvent) => void) => {
      holder.cb = cb
      return () => {}
    })

    await store.open(1)
    const terminal = event('succeeded')
    terminal.seq = 9
    holder.cb?.(terminal)
    holder.cb?.(terminal)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(store.events).toHaveLength(1)
    expect(mocks.getBatch).toHaveBeenCalledTimes(2)
  })

  it('SSE 断线时显示连接中断并轮询快照，onOpen 恢复后停止', async () => {
    vi.useFakeTimers()
    try {
      const store = useBatchStore()
      const holder: { hooks?: { onOpen?: () => void; onError?: () => void } } = {}
      mocks.getBatch.mockResolvedValue(snapshot('running'))
      mocks.openProgress.mockImplementation((_id: number, _cb: (e: StageEvent) => void,
        hooks: { onOpen?: () => void; onError?: () => void }) => {
        holder.hooks = hooks
        return () => {}
      })

      await store.open(1)
      holder.hooks?.onError?.()
      expect(store.connectionLost).toBe(true)

      await vi.advanceTimersByTimeAsync(4000)
      expect(mocks.getBatch).toHaveBeenCalledTimes(2)

      holder.hooks?.onOpen?.()
      expect(store.connectionLost).toBe(false)
      await vi.advanceTimersByTimeAsync(4000)
      expect(mocks.getBatch).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('open 失败时设置 error 且不订阅', async () => {
    const store = useBatchStore()
    mocks.getBatch.mockRejectedValue(new Error('批次不存在'))
    await store.open(1)
    expect(store.error).toBe('批次不存在')
    expect(store.current).toBeNull()
    expect(mocks.openProgress).not.toHaveBeenCalled()
  })

  it('stopProgress 清空旧批次状态', async () => {
    const store = useBatchStore()
    mocks.getBatch.mockResolvedValue(snapshot('succeeded'))
    mocks.openProgress.mockReturnValue(() => {})
    await store.open(1)
    store.stopProgress()
    expect(store.current).toBeNull()
    expect(store.events).toHaveLength(0)
    expect(store.error).toBe('')
  })
})
