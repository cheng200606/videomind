import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { useThemeMode } from '@/composables/useTheme'

// vitest 下按需组件自动引入被跳过：手动 stub el-alert
const stubs = { 'el-alert': { template: '<div class="alert-stub"><slot /></div>' } }

const initialize = vi.fn()
// 显式声明入参：mermaid.render(id, code) —— 后面的归一化断言要读第 2 个参数
const renderMock = vi.fn(async (_id: string, _code: string) => ({ svg: '<svg>ok</svg>' }))

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

describe('MermaidView 首行 flowchart-elk 归一化', () => {
  afterEach(() => {
    initialize.mockClear()
    renderMock.mockClear()
  })

  /** renderMock 第 2 个入参就是交给 mermaid 的图定义 */
  async function renderedCode(code: string) {
    mount(MermaidView, { props: { code }, global: { stubs } })
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()
    return renderMock.mock.calls.at(-1)![1] as string
  }

  it('把首行 flowchart-elk 收敛成 flowchart，且正文逐字不动', async () => {
    // 刻意带缩进、带注释、带中文标签和样式行，覆盖"只有首行能被改"的边界
    const body = [
      '  A[开始] --> B{判断}',
      '  %% 注释不能动',
      '  B -->|是| C[分支一]',
      '  B -->|否| D[分支二]',
      '  classDef hot fill:#f00'
    ].join('\n')
    const code = `flowchart-elk TD\n${body}`

    const got = await renderedCode(code)

    expect(got.startsWith('flowchart-elk')).toBe(false)
    expect(got.split('\n')[0]).toBe('flowchart TD')
    // 结构一致：除首行关键字外，其余每个字符都必须与原文相同
    expect(got.slice(got.indexOf('\n'))).toBe(code.slice(code.indexOf('\n')))
  })

  it('归一化后仍能渲染出 svg', async () => {
    const wrapper = mount(MermaidView, {
      props: { code: 'flowchart-elk TD\nA-->B' },
      global: { stubs }
    })
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()
    expect(renderMock.mock.calls.at(-1)![1]).toBe('flowchart TD\nA-->B')
    expect(wrapper.find('.diagram').html()).toContain('<svg')
  })

  it('非 elk 图与正文里出现的 flowchart-elk 字样都不受影响', async () => {
    const plain = 'flowchart TD\nA-->B'
    expect(await renderedCode(plain)).toBe(plain)

    // 只在首行锚定：正文里出现这个单词不能被改写
    const withMention = 'flowchart LR\nA[flowchart-elk 说明]-->B'
    expect(await renderedCode(withMention)).toBe(withMention)
  })

  it('保留首行原有缩进，不把行首空白吃掉', async () => {
    const got = await renderedCode('   flowchart-elk TD\nA-->B')
    expect(got).toBe('   flowchart TD\nA-->B')
  })
})
