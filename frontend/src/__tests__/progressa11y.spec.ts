import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getBatch: vi.fn(),
  openProgress: vi.fn()
}))

vi.mock('@/api/client', () => ({
  getBatch: mocks.getBatch,
  listBatches: vi.fn(),
  openProgress: mocks.openProgress,
  reparseBatch: vi.fn(),
  retryVideo: vi.fn()
}))

import BatchProgressView from '@/views/BatchProgressView.vue'

/**
 * 进度事件流是纯视觉的 el-timeline：SSE 推进时屏幕阅读器原本完全静默。
 * 这里锁定 P0-3 补上的三个可访问性事实。
 * 只断言结构与属性——vitest 下 unplugin-vue-components 不生效，el-* 全是 stub。
 */

const stubs = {
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-tag': { template: '<span><slot /></span>' },
  // el-table 的列插槽靠作用域参数 row 求值，stub 不提供 row 会直接炸；本用例不关心表格
  'el-table': { template: '<div />' },
  'el-table-column': { template: '<div />' },
  'el-timeline': { template: '<div class="tl-stub" v-bind="$attrs"><slot /></div>' },
  'el-timeline-item': { template: '<div><slot /></div>' },
  'el-alert': { template: '<div><slot /></div>' },
  'el-progress': { template: '<div />' },
  'el-select': { template: '<div><slot /></div>' },
  'el-option': { template: '<div><slot /></div>' },
  'el-empty': { template: '<div />' },
  'el-skeleton': { template: '<div />' },
  PageHeader: { template: '<div><slot name="tag" /><slot name="actions" /><slot /></div>' }
}

function snapshot() {
  return {
    id: 1,
    name: 'X',
    status: 'running',
    videos: [{
      id: 10, file_name: 'demo.mp4', media_url: '/media/1_demo.mp4', duration_ms: 1000,
      status: 'running', error: '', stages: {
        transcribe: 'pending', visual: 'pending', structure: 'pending', artifact: 'pending'
      }
    }]
  }
}

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/batches/:id', name: 'progress', component: BatchProgressView }]
  })
  await router.push('/batches/1')
  await router.isReady()
  const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router], stubs } })
  await flushPromises()
  return wrapper
}

describe('批次进度页的进度播报', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mocks.getBatch.mockResolvedValue(snapshot())
    mocks.openProgress.mockReturnValue(() => {})
  })

  it('时间轴有可访问名称，live region 独立于时间轴存在', async () => {
    const wrapper = await mountView()

    // ① live region 存在且是礼貌播报
    const live = wrapper.find('[role="status"][aria-live="polite"]')
    expect(live.exists()).toBe(true)
    expect(live.attributes('aria-atomic')).toBe('true')

    // ② 它不在时间轴内部，否则每 push 一条就会把整条时间轴重播一遍
    const timeline = wrapper.find('.tl-stub')
    expect(timeline.exists()).toBe(true)
    expect(timeline.find('[role="status"]').exists()).toBe(false)

    // ③ 时间轴有可访问名称
    expect(timeline.attributes('aria-label')).toBe('解析事件流，最新事件在最上方')
  })

  it('播报文本取最新一条事件，阶段与状态走中文映射', async () => {
    const wrapper = await mountView()
    const store = (await import('@/stores/batch')).useBatchStore()

    store.events = [{
      batch_id: 1, video_id: 10, stage: 'transcribe', status: 'done',
      message: '', ts: '2026-11-06T00:00:00+00:00', seq: 1
    }]
    await flushPromises()

    expect(wrapper.find('[role="status"]').text()).toBe('① ASR 转写：完成')
  })
})
