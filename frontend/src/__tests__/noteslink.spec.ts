import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ItemDetail } from '@/api/types'

const mocks = vi.hoisted(() => ({
  getItem: vi.fn()
}))

vi.mock('@/api/client', () => ({
  getItem: mocks.getItem,
  addNote: vi.fn(),
  revise: vi.fn(),
  updateNote: vi.fn()
}))

// CodeMirror 在 jsdom 下没有 getClientRects，编辑器本体与断言无关
vi.mock('md-editor-v3', () => ({
  MdEditor: { template: '<div class="md-editor-stub" />' }
}))

import NotesView from '@/views/NotesView.vue'

const item: ItemDetail = {
  id: 42,
  video_id: 7,
  video_name: 'demo.mp4',
  type: 'key_points',
  title: '某个知识点',
  content: '讲义正文',
  confidence: 'explicit',
  anchor_ms: 12000,
  ordinal: 0,
  payload: {},
  evidence: null,
  conflicts: [],
  revisions: [],
  notes: []
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/notes/:id', name: 'notes', component: NotesView },
      { path: '/videos/:id', name: 'workbench', component: { template: '<div />' } }
    ]
  })
}

const stubs = {
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  // 真 el-link 带 href 时可键盘到达；stub 保留同样的 a[href] 供断言
  'el-link': { props: ['href'], template: '<a :href="href"><slot /></a>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-tag': { template: '<span><slot /></span>' },
  'el-icon': { template: '<span><slot /></span>' },
  'el-alert': { template: '<div><slot /></div>' },
  'el-skeleton': { template: '<div />' },
  'el-tabs': { template: '<div><slot /></div>' },
  'el-tab-pane': { template: '<div><slot /></div>' },
  'el-select': { template: '<div><slot /></div>' },
  'el-option': { template: '<div><slot /></div>' },
  'el-timeline': { template: '<div><slot /></div>' },
  'el-timeline-item': { template: '<div><slot /></div>' },
  PageHeader: { template: '<div><slot /></div>' },
  ConfidenceTag: { template: '<span>明述</span>' },
  MdEditor: true
}

describe('笔记来源时间 → 原片反向跳转', () => {
  beforeEach(() => {
    mocks.getItem.mockReset()
    mocks.getItem.mockResolvedValue(item)
  })

  it('时间戳是可键盘到达的链接，指向工作台并带 ?item= 深链', async () => {
    const router = makeRouter()
    await router.push('/notes/42')
    await router.isReady()

    // 通过 RouterView 挂载，让 useLeaveGuard 拿到真实的路由上下文
    const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router], stubs } })
    await flushPromises()

    const link = wrapper.find('a[href="/videos/7?item=42"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toBe('0:12')

    await link.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('workbench')
    expect(router.currentRoute.value.params.id).toBe('7')
    expect(router.currentRoute.value.query.item).toBe('42')
  })
})
