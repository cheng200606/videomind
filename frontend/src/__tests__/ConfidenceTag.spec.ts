import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ConfidenceTag from '@/components/ConfidenceTag.vue'
import type { Confidence } from '@/api/types'

const CASES: { confidence: Confidence; label: string }[] = [
  { confidence: 'explicit', label: '明述' },
  { confidence: 'inferred', label: '推断' },
  { confidence: 'low', label: '低置信' }
]

// vitest 下 el-* 不会自动注册；用轻量 stub 渲染插槽，只断言中文映射
const stubs = { 'el-tag': { template: '<span><slot /></span>' } }

describe('三档置信度标签（F4 不确定性分级）', () => {
  for (const { confidence, label } of CASES) {
    it(`${confidence} 渲染为「${label}」`, () => {
      const wrapper = mount(ConfidenceTag, { props: { confidence }, global: { stubs } })
      expect(wrapper.text()).toContain(label)
    })
  }
})
