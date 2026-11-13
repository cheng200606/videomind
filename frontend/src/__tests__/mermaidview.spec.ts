import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { useThemeMode } from '@/composables/useTheme'

// vitest 下按需组件自动引入被跳过：手动 stub el-alert
const stubs = { 'el-alert': { template: '<div class="alert-stub"><slot /></div>' } }

const initialize = vi.fn()
const renderMock = vi.fn(async () => ({ svg: '<svg>ok</svg>' }))

vi.mock('mermaid', () => ({
  default: { initialize, render: renderMock }
}))

import MermaidView from '@/components/MermaidView.vue'

describe('MermaidView 主题感知渲染', () => {
  afterEach(() => {
    initialize.mockClear()
    renderMock.mockClear()
    const { setMode } = useThemeMode()
    setMode('light')
  })

  it('按当前主题初始化 mermaid 并渲染 svg', async () => {
    const wrapper = mount(MermaidView, {
      props: { code: 'flowchart TD\nA-->B' },
      global: { stubs }
    })
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()
    expect(initialize).toHaveBeenCalled()
    const cfg = initialize.mock.calls.at(-1)![0]
    expect(cfg.themeVariables.primaryTextColor).toBe('#1f2937')   // 亮色默认
    expect(wrapper.find('.diagram').html()).toContain('<svg')
    expect(wrapper.find('.alert-stub').exists()).toBe(false)
  })

  it('切到暗色主题时用暗色变量重新初始化并重渲染', async () => {
    const wrapper = mount(MermaidView, {
      props: { code: 'flowchart TD\nA-->B' },
      global: { stubs }
    })
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()
    const before = initialize.mock.calls.length

    const { setMode } = useThemeMode()
    setMode('dark')
    await nextTick()
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    expect(initialize.mock.calls.length).toBeGreaterThan(before)
    const cfg = initialize.mock.calls.at(-1)![0]
    expect(cfg.themeVariables.primaryTextColor).toBe('#e5e7eb')   // 暗色对位
    expect(wrapper.find('.diagram').html()).toContain('<svg')
  })

  it('渲染失败时降级为告警 + 原文，不白屏', async () => {
    renderMock.mockRejectedValueOnce(new Error('bad diagram syntax'))
    const wrapper = mount(MermaidView, {
      props: { code: 'flowchart TD\n坏语法' },
      global: { stubs }
    })
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()
    expect(wrapper.find('.alert-stub').exists()).toBe(true)   // stub 不透传 title，只验证降级区块出现
    expect(wrapper.props('code')).toContain('坏语法')
    expect(wrapper.find('.raw').text()).toContain('坏语法')
  })
})
