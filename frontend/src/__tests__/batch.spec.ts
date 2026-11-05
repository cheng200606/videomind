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
  openProgress: mocks.openProgress
}))

import { useBatchStore } from '@/stores/batch'

function event(status: string): StageEvent {
  return { batch_id: 1, video_id: null, stage: 'batch', status, message: '', ts: '2026-11-06T00:00:00+00:00' }
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
    expect(mocks.openProgress).toHaveBeenCalledWith(1, expect.any(Function))
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
})
