import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ConfidenceTag from '@/components/ConfidenceTag.vue'
import type { Confidence } from '@/api/types'

const CASES: { confidence: Confidence; label: string }[] = [
  { confidence: 'explicit', label: '明述' },
  { confidence: 'inferred', label: '推断' },
  { confidence: 'low', label: '低置信' }
]

describe('三档置信度标签（F4 不确定性分级）', () => {
  for (const { confidence, label } of CASES) {
    it(`${confidence} 渲染为「${label}」`, () => {
      const wrapper = mount(ConfidenceTag, { props: { confidence } })
      expect(wrapper.text()).toContain(label)
    })
  }
})
