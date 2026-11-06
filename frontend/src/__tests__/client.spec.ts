import { describe, expect, it } from 'vitest'

import { exportUrl, formatDetail, mediaUrl } from '@/api/client'

describe('URL 拼装', () => {
  it('mediaUrl 从绝对路径取媒体文件名（上传落盘带批次 id 前缀，批内唯一）', () => {
    expect(mediaUrl('D:\\data\\media\\1_vue3_lecture.mp4')).toBe('/media/1_vue3_lecture.mp4')
    expect(mediaUrl('/srv/data/media/2_code_demo.mp4')).toBe('/media/2_code_demo.mp4')
  })

  it('exportUrl 指向批次导出端点', () => {
    expect(exportUrl(3)).toBe('/api/batches/3/export.md')
  })
})

describe('FastAPI 422 detail 可读化', () => {
  it('数组 detail 转成「字段：中文原因」，pydantic 英文 msg 做常见模式映射', () => {
    expect(formatDetail([
      { loc: ['body', 'anchor_ms'], msg: 'Input should be a valid integer' }
    ])).toBe('anchor_ms：应为整数')
    expect(formatDetail([
      { loc: ['body'], msg: 'Field required' }
    ])).toBe('缺少必填参数')
  })

  it('无法映射的 msg 保留原文（后端 v0.11 已在源头中文化，这里只兜底）', () => {
    expect(formatDetail([
      { loc: ['query', 'type'], msg: 'unexpected value' }
    ])).toBe('type：unexpected value')
  })

  it('字符串 detail 原样返回，空值返回空串', () => {
    expect(formatDetail('批次不存在')).toBe('批次不存在')
    expect(formatDetail(undefined)).toBe('')
  })
})
