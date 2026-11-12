import { describe, expect, it } from 'vitest'

import { highlightSegments, matchSnippet } from '@/api/highlight'

describe('highlightSegments', () => {
  it('把命中段与普通段分开，大小写不敏感', () => {
    expect(highlightSegments('Ref 响应式与 ref() 用法', 'ref')).toEqual([
      { text: 'Ref', hit: true },
      { text: ' 响应式与 ', hit: false },
      { text: 'ref', hit: true },
      { text: '() 用法', hit: false },
    ])
  })

  it('正则元字符按字面匹配：搜索 (a) 不会当成分组', () => {
    const segs = highlightSegments('调用 (a) 函数', '(a)')
    expect(segs).toEqual([
      { text: '调用 ', hit: false },
      { text: '(a)', hit: true },
      { text: ' 函数', hit: false },
    ])
  })

  it('空关键词与无命中都返回单段未命中；空文本安全', () => {
    expect(highlightSegments('任意文本', '')).toEqual([{ text: '任意文本', hit: false }])
    expect(highlightSegments('任意文本', '   ')).toEqual([{ text: '任意文本', hit: false }])
    expect(highlightSegments('abc', 'xyz').every((s) => !s.hit)).toBe(true)
    expect(highlightSegments('', 'ref')).toEqual([{ text: '', hit: false }])
  })
})

describe('matchSnippet', () => {
  it('围绕首个命中截取并加省略号，不切断命中词', () => {
    const text = '前'.repeat(50) + '关键词出现在中间位置' + '后'.repeat(50)
    const s = matchSnippet(text, '关键词', 10)
    expect(s.startsWith('…')).toBe(true)
    expect(s.endsWith('…')).toBe(true)
    expect(s).toContain('关键词')
  })

  it('无命中从头截取；短文本原样返回；空关键词原样返回', () => {
    expect(matchSnippet('a'.repeat(120), 'zzz', 40)).toBe('a'.repeat(80) + '…')
    expect(matchSnippet('短文本', 'zzz')).toBe('短文本')
    expect(matchSnippet('原样返回', '   ')).toBe('原样返回')
  })
})
