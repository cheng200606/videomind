import { describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

import { useProgressiveList } from '@/composables/useProgressiveList'

function makeSource(n: number) {
  return ref(Array.from({ length: n }, (_, i) => i))
}

describe('useProgressiveList', () => {
  it('首屏只挂 step 条，loadMore 追加且不超过总量', () => {
    const source = makeSource(950)
    const { visible, hasMore, loadMore } = useProgressiveList(source, 400)
    expect(visible.value).toHaveLength(400)
    expect(hasMore.value).toBe(true)
    loadMore()
    expect(visible.value).toHaveLength(800)
    loadMore()
    expect(visible.value).toHaveLength(950)
    expect(hasMore.value).toBe(false)
    loadMore()
    expect(visible.value).toHaveLength(950), '超量后 loadMore 是空操作'
  })

  it('数据源整体替换时窗口重置（切换视频不残留滚动加载进度）', async () => {
    const source = makeSource(1000)
    const { visible, visibleCount, reset } = useProgressiveList(source, 400)
    visibleCount.value = 900
    source.value = Array.from({ length: 1000 }, (_, i) => i + 10000)
    await nextTick()
    expect(visible.value[0]).toBe(10000)
    expect(visible.value).toHaveLength(400)
    reset()
    expect(visible.value).toHaveLength(400)
  })

  it('短列表一次挂全，hasMore 为 false', () => {
    const source = makeSource(50)
    const { visible, hasMore } = useProgressiveList(source, 400)
    expect(visible.value).toHaveLength(50)
    expect(hasMore.value).toBe(false)
  })

  it('bindSentinel(null) 安全返回；哨兵进入视口触发追加；组件实例形式取 $el', () => {
    const source = makeSource(1000)
    const { bindSentinel, visible, hasMore } = useProgressiveList(source, 400)

    expect(bindSentinel(null)).toBeUndefined()

    const realIO = globalThis.IntersectionObserver
    let callback: IntersectionObserverCallback = () => {}
    class FakeObserver {
      constructor(cb: IntersectionObserverCallback) { callback = cb }
      observe = vi.fn()
      disconnect = vi.fn()
      unobserve = vi.fn()
    }
    ;(globalThis as Record<string, unknown>).IntersectionObserver = FakeObserver

    const sentinel = document.createElement('div')
    bindSentinel(sentinel)
    callback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
    expect(visible.value).toHaveLength(800)
    expect(hasMore.value).toBe(true)

    // 模板 ref 也可能给组件实例：取 $el 作为观察目标
    const instance = { $el: document.createElement('div') } as never
    bindSentinel(instance)
    callback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
    expect(visible.value).toHaveLength(1000)

    bindSentinel(null)   // 解绑路径不抛错
    ;(globalThis as Record<string, unknown>).IntersectionObserver = realIO
  })
})
