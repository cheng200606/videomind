/**
 * SSE 收流生命周期（v0.17 质量门 P0）
 *
 * 背景：AGENTS.md「已知坑」点名——前端 EventSource 收到终态事件必须主动 close()，
 * 否则浏览器 ~3s 自动重连、服务端再补一条终态，形成无限重复收事件。
 * 该逻辑在 `client.ts` 的 openProgress 里，但 batch.spec.ts 用 vi.mock 把整个
 * `@/api/client` 换掉了，真实实现从未被测过。本文件直接测真实实现。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { StageEvent } from '@/api/types'

/** 最小 EventSource 替身：只实现 client.ts 真正用到的那几个成员 */
class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private listeners = new Map<string, ((ev: MessageEvent) => void)[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, handler: (ev: MessageEvent) => void) {
    const list = this.listeners.get(type) ?? []
    list.push(handler)
    this.listeners.set(type, list)
  }

  close() {
    this.closed = true
  }

  /** 模拟服务端推一条 stage 事件 */
  emit(event: StageEvent) {
    for (const handler of this.listeners.get('stage') ?? []) {
      handler({ data: JSON.stringify(event) } as MessageEvent)
    }
  }

  static reset() {
    FakeEventSource.instances = []
  }
}

function stageEvent(overrides: Partial<StageEvent> = {}): StageEvent {
  return {
    batch_id: 1,
    video_id: null,
    stage: 'batch',
    status: 'running',
    message: '',
    ts: '2026-11-21T00:00:00+00:00',
    ...overrides
  }
}

beforeEach(() => {
  FakeEventSource.reset()
  vi.stubGlobal('EventSource', FakeEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/** client.ts 在函数内引用全局 EventSource，必须动态 import 以吃到 stub */
async function loadOpenProgress() {
  const mod = await import('@/api/client')
  return mod.openProgress
}

describe('SSE 收流：终态必须主动 close（AGENTS.md 已知坑）', () => {
  it('整批终态事件后立即 close，不再让 EventSource 自动重连', async () => {
    const openProgress = await loadOpenProgress()
    const seen: StageEvent[] = []
    openProgress(7, (e) => seen.push(e))

    const source = FakeEventSource.instances[0]
    expect(source).toBeTruthy()
    expect(source.url).toContain('/api/batches/7/progress')

    // 非终态：不能关
    source.emit(stageEvent({ status: 'running' }))
    expect(source.closed).toBe(false)

    // 整批终态（video_id 为空 + succeeded）：必须关
    source.emit(stageEvent({ status: 'succeeded', video_id: null }))
    expect(source.closed).toBe(true)
    expect(seen).toHaveLength(2)
  })

  it('单条视频终态（video_id 非空）不算整批结束，不得收流', async () => {
    const openProgress = await loadOpenProgress()
    openProgress(8, () => {})

    const source = FakeEventSource.instances[0]
    // stage=batch 但 video_id 非空 → 单条视频终态，整批还在跑
    source.emit(stageEvent({ status: 'succeeded', video_id: 42 }))
    expect(source.closed).toBe(false)

    // 非 batch 阶段的 succeeded 同理不能误判
    source.emit(stageEvent({ status: 'succeeded', stage: 'transcribe', video_id: null }))
    expect(source.closed).toBe(false)
  })

  it('三条终态值（succeeded / partial / failed）都收流', async () => {
    const openProgress = await loadOpenProgress()
    for (const status of ['succeeded', 'partial', 'failed']) {
      FakeEventSource.reset()
      openProgress(9, () => {})
      const source = FakeEventSource.instances[0]
      source.emit(stageEvent({ status }))
      expect(source.closed, status).toBe(true)
    }
  })

  it('返回的取消函数可立刻 close（组件卸载路径）', async () => {
    const openProgress = await loadOpenProgress()
    const cancel = openProgress(10, () => {})
    const source = FakeEventSource.instances[0]
    expect(source.closed).toBe(false)
    cancel()
    expect(source.closed).toBe(true)

    // 关闭后即便再来终态事件也不应重复处理（closed 标记已置位）
    source.emit(stageEvent({ status: 'succeeded' }))
    expect(source.closed).toBe(true)
  })

  it('onerror 不主动 close（要靠自动重连 + 快照轮询兜底）', async () => {
    const openProgress = await loadOpenProgress()
    const onError = vi.fn()
    openProgress(11, () => {}, { onError })

    const source = FakeEventSource.instances[0]
    source.onerror?.()
    expect(onError).toHaveBeenCalledTimes(1)
    expect(source.closed).toBe(false)
  })
})
