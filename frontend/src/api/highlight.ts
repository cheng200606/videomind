/**
 * 检索命中高亮的纯函数工具：分段输出，模板里循环渲染，不做 HTML 拼接（规避 XSS）。
 * 关键词按字面处理——% 与 _ 是普通字符（与后端 LIKE 转义口径一致），正则元字符单独转义。
 */

export interface HighlightSegment {
  text: string
  hit: boolean
}

const REGEX_SPECIAL = /[.*+?^${}()|[\]\\]/g

function escapeRegExp(raw: string): string {
  return raw.replace(REGEX_SPECIAL, '\\$&')
}

/** 把文本按关键词切成命中/未命中段；关键词为空或文本无命中时返回单段未命中。大小写不敏感。 */
export function highlightSegments(text: string, query: string): HighlightSegment[] {
  const q = query.trim()
  if (!q || !text) return [{ text, hit: false }]
  const parts = text.split(new RegExp(`(${escapeRegExp(q)})`, 'gi'))
  const lower = q.toLowerCase()
  return parts
    .filter((p) => p !== '')
    .map((p) => ({ text: p, hit: p.toLowerCase() === lower }))
}

/** 围绕首个命中截取摘要；无命中时从头截取。始终整词边界无关，只保证不切断命中词。 */
export function matchSnippet(text: string, query: string, radius = 40): string {
  const q = query.trim()
  if (!q) return text
  const idx = text.toLowerCase().indexOf(q.toLowerCase())
  if (idx < 0) return text.length > radius * 2 ? `${text.slice(0, radius * 2)}…` : text
  const start = Math.max(0, idx - radius)
  const end = Math.min(text.length, idx + q.length + radius)
  const head = start > 0 ? '…' : ''
  const tail = end < text.length ? '…' : ''
  return `${head}${text.slice(start, end)}${tail}`
}
