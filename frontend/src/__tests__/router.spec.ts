import { describe, expect, it } from 'vitest'

import router from '@/router'

describe('路由表', () => {
  it('跨视频检索是独立侧边栏入口 /search', () => {
    const r = router.resolve('/search')
    expect(r.name).toBe('search')
    expect(r.meta.title).toBe('知识检索')
  })

  it('详情页路由保持原有路径与标题', () => {
    expect(router.resolve('/batches/1').name).toBe('progress')
    expect(router.resolve('/videos/2').name).toBe('workbench')
    expect(router.resolve('/notes/3').name).toBe('notes')
    expect(router.resolve('/batches/1/export').name).toBe('export')
    expect(router.resolve('/upload').meta.title).toBe('批量上传')
  })

  it('笔记跳回原片：工作台深链带视频 id 与条目 item 参数', () => {
    // NotesView.sourceRoute 使用的就是这一组 name/params/query
    const r = router.resolve({
      name: 'workbench', params: { id: '7' }, query: { item: '42' }
    })
    expect(r.name).toBe('workbench')
    expect(r.params.id).toBe('7')
    expect(r.query.item).toBe('42')
    expect(r.href).toBe('/videos/7?item=42')
  })

  it('未知路径仍落到 404 页', () => {
    const r = router.resolve('/no/such/page')
    expect(r.name).toBe('not-found')
  })
})
