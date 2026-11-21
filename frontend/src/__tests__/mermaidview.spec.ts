// 本仓 tsconfig 的 types 白名单只有 vite/client（无 @types/node），但 vitest 本就跑在 Node 下，
// node:fs 一定可用——这里只需压制 vue-tsc 的类型解析，不动 tsconfig / package.json。
// @ts-ignore
import { readFileSync } from 'node:fs'
// @ts-ignore
import { dirname, resolve } from 'node:path'
// @ts-ignore
import { fileURLToPath } from 'node:url'

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

/**
 * theme.css 与 MermaidView 的 themeVariables 是两份必须同步的常量：mermaid 读不到 CSS 变量，
 * 只能把值写死在 JS 里。改了 theme.css 主色却忘了同步这里，页面不会出现编译错误，只会悄悄
 * 配出色差。这个 describe 直接解析两份源文件比对——vitest 守不住 CSS 对比度，但能守住「同值」。
 */
describe('mermaid 主题常量与 theme.css 同源（v0.17 P1-5）', () => {
  const here = dirname(fileURLToPath(import.meta.url))
  const themeCss = readFileSync(resolve(here, '../styles/theme.css'), 'utf-8')
  const vueSource = readFileSync(resolve(here, '../components/MermaidView.vue'), 'utf-8')

  // 按 :root:root.dark 分段：亮块在前，暗块在后，同名的 CSS 变量各取一次
  const darkIdx = themeCss.indexOf(':root:root.dark')
  const lightBlock = themeCss.slice(0, darkIdx)
  const darkBlock = themeCss.slice(darkIdx)

  function cssVar(block: string, name: string): string {
    const m = block.match(new RegExp(`${name}\\s*:\\s*(#[0-9a-fA-F]{6})`))
    if (!m) throw new Error(`theme.css 未找到 ${name}`)
    return m[1].toLowerCase()
  }

  // MermaidView 的 themeVariables 里，每个 key 出现两次：先暗（dark?）后亮（:）
  function mermaidPair(key: string): [dark: string, light: string] {
    const hits = [...vueSource.matchAll(new RegExp(`${key}\\s*:\\s*'(#[0-9a-fA-F]{6})'`, 'g'))]
      .map((m) => m[1].toLowerCase())
    if (hits.length !== 2) throw new Error(`MermaidView.vue 的 ${key} 期望 2 处（暗/亮），实际 ${hits.length}`)
    return [hits[0], hits[1]]
  }

  it('primaryColor 对齐 --el-color-primary-light-8/-9', () => {
    const [dark, light] = mermaidPair('primaryColor')
    expect(light).toBe(cssVar(lightBlock, '--el-color-primary-light-9'))  // #eef3fd
    expect(dark).toBe(cssVar(darkBlock, '--el-color-primary-light-8'))    // #182c53
  })

  it('primaryTextColor 对齐两套 --vm-text', () => {
    const [dark, light] = mermaidPair('primaryTextColor')
    expect(light).toBe(cssVar(lightBlock, '--vm-text'))  // #1f2937
    expect(dark).toBe(cssVar(darkBlock, '--vm-text'))    // #e5e7eb
  })

  it('primaryBorderColor 与 lineColor 都对齐 --el-color-primary', () => {
    const border = mermaidPair('primaryBorderColor')
    const line = mermaidPair('lineColor')
    expect(border).toEqual(line)  // 两处必须同值，不能一个跟了主色一个没跟
    expect(border[0]).toBe(cssVar(darkBlock, '--el-color-primary'))    // 暗 #6f95e3
    expect(border[1]).toBe(cssVar(lightBlock, '--el-color-primary'))   // 亮 #3d6fd6
  })
})
