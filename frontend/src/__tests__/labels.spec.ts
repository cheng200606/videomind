import { describe, expect, it } from 'vitest'

import {
  ARTIFACT_LABEL, EVENT_STAGE_LABEL, REVISION_LABEL, REVISION_TRANSITIONS, STAGE_LABEL,
  STAGE_STATUS_LABEL, STATUS_LABEL, STATUS_TYPE, clock, fmtTime
} from '@/api/labels'

describe('枚举中文映射', () => {
  it('批次/视频状态全量覆盖且有配色区分（failed 不再是灰色）', () => {
    for (const s of ['pending', 'running', 'succeeded', 'partial', 'failed']) {
      expect(STATUS_LABEL[s], s).toBeTruthy()
      expect(STATUS_TYPE[s], s).toBeTruthy()
    }
    expect(STATUS_TYPE.failed).toBe('danger')
    expect(STATUS_TYPE.partial).toBe('warning')
    expect(STATUS_LABEL.succeeded).toBe('成功')
  })

  it('四阶段矩阵与事件流条目（batch / video_start）都有中文名，且互不串用', () => {
    expect(Object.keys(STAGE_LABEL)).toEqual(['transcribe', 'visual', 'structure', 'artifact'])
    expect(STAGE_LABEL.transcribe).toContain('ASR')
    expect(EVENT_STAGE_LABEL.batch).toBe('批次')
    expect(EVENT_STAGE_LABEL.video_start).toBe('开始解析')
    expect(STAGE_STATUS_LABEL.video_start).toBe('开始解析')
    expect(STAGE_STATUS_LABEL.skipped).toBe('降级跳过')
  })

  it('产物类型与讲义状态映射齐备', () => {
    expect(ARTIFACT_LABEL.summary).toBe('内容总结')
    expect(REVISION_LABEL.pending_confirm).toBe('待确认')
  })
})

describe('讲义状态机前端禁用表', () => {
  it('与后端 REVISION_TRANSITIONS 同源：合法跳转可点，非法跳转禁用', () => {
    expect(REVISION_TRANSITIONS.draft).toEqual(['pending_confirm'])
    expect(REVISION_TRANSITIONS.confirmed).toContain('revised')
    expect(REVISION_TRANSITIONS.revised).toEqual(['pending_confirm'])
    expect(REVISION_TRANSITIONS.pending_confirm).toContain('draft')
  })
})

describe('展示格式化', () => {
  it('clock 进位：不足 1 小时 m:ss，超过 1 小时 h:mm:ss', () => {
    expect(clock(0)).toBe('0:00')
    expect(clock(19000)).toBe('0:19')
    expect(clock(4 * 60000)).toBe('4:00')
    expect(clock((3600 + 75) * 1000)).toBe('1:01:15')
  })

  it('fmtTime 把带时区的 UTC ISO 转本地时间；非法输入原样返回', () => {
    expect(fmtTime('2026-11-05T17:40:45+00:00')).not.toContain('T')
    expect(fmtTime('不是时间')).toBe('不是时间')
  })
})
