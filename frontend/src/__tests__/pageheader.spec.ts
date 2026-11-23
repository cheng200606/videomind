import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PageHeader from '@/components/PageHeader.vue'

// vitest 下按需组件自动引入被跳过（见 vite.config.ts）：手动注册 el-* 轻量 stub，
// 单测只断言文本与层级，顺带消除 "Failed to resolve component" 告警噪声。
const stubs = {
  'el-breadcrumb': { template: '<nav><slot /></nav>' },
  'el-breadcrumb-item': { template: '<span><slot /></span>' }
}

describe('统一页头（面包屑承担数据层级）', () => {
  it('渲染面包屑层级、页标题与副标题', () => {
    const wrapper = mount(PageHeader, {
      props: {
        title: '批次进度',
        subtitle: '共 3 个视频',
        crumbs: [{ label: '视频库', to: '/' }, { label: 'demo 批次' }]
      },
      global: { stubs }
    })
    expect(wrapper.text()).toContain('视频库')
    expect(wrapper.text()).toContain('demo 批次')
    expect(wrapper.text()).toContain('批次进度')
    expect(wrapper.text()).toContain('共 3 个视频')
  })

  it('无面包屑时不渲染导航区（根页面场景）', () => {
    const wrapper = mount(PageHeader, { props: { title: '视频库' }, global: { stubs } })
    expect(wrapper.find('.crumb').exists()).toBe(false)
    expect(wrapper.text()).toContain('视频库')
  })
})
