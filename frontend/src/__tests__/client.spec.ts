import { describe, expect, it } from 'vitest'

import { exportUrl, mediaUrl } from '@/api/client'

describe('URL 拼装', () => {
  it('mediaUrl 从绝对路径取媒体文件名（上传落盘带批次 id 前缀，批内唯一）', () => {
    expect(mediaUrl('D:\\data\\media\\1_vue3_lecture.mp4')).toBe('/media/1_vue3_lecture.mp4')
    expect(mediaUrl('/srv/data/media/2_code_demo.mp4')).toBe('/media/2_code_demo.mp4')
  })

  it('exportUrl 指向批次导出端点', () => {
    expect(exportUrl(3)).toBe('/api/batches/3/export.md')
  })
})
