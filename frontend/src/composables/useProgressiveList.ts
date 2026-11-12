import { computed, onBeforeUnmount, ref, watch, type ComponentPublicInstance, type Ref } from 'vue'

/**
 * 长列表渐进渲染：首屏只挂 step 条，哨兵进入视口再追加——零依赖替代虚拟滚动。
 * 用于工作台上限 5000 段的转写这类「读得完但挂不全」的列表；
 * IntersectionObserver 不可用的环境（jsdom）静默跳过，调用方用「显示更多」按钮兜底。
 */
export function useProgressiveList<T>(source: Ref<T[]>, step = 400) {
  const visibleCount = ref(step)
  const visible = computed(() => source.value.slice(0, visibleCount.value))
  const hasMore = computed(() => visibleCount.value < source.value.length)

  let observer: IntersectionObserver | null = null

  function loadMore() {
    if (hasMore.value) {
      visibleCount.value = Math.min(visibleCount.value + step, source.value.length)
    }
  }

  /** 换数据源即重置窗口（transcript.value 换数组引用即触发），避免上一条视频的滚动加载进度延续 */
  watch(source, () => {
    visibleCount.value = step
  })

  /** 直接可作模板 :ref 回调（元素或组件实例都接，取 $el）；解绑传 null。 */
  function bindSentinel(el: Element | ComponentPublicInstance | null) {
    observer?.disconnect()
    observer = null
    const target = el instanceof Element ? el : ((el as ComponentPublicInstance | null)?.$el as Element | null | undefined) ?? null
    if (!target || typeof IntersectionObserver === 'undefined') return
    observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) loadMore()
    })
    observer.observe(target)
  }

  onBeforeUnmount(() => observer?.disconnect())

  return { visible, hasMore, visibleCount, loadMore, reset: () => { visibleCount.value = step }, bindSentinel }
}
