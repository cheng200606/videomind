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
  it('数组 detail 转成字段：原因，不再把原始 JSON 甩给用户', () => {
    expect(formatDetail([
      { loc: ['body', 'anchor_ms'], msg: 'Input should be a valid integer' }
    ])).toBe('anchor_ms：Input should be a valid integer')
  })

  it('字符串 detail 原样返回，空值返回空串', () => {
    expect(formatDetail('批次不存在')).toBe('批次不存在')
    expect(formatDetail(undefined)).toBe('')
  })
})
