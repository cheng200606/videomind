<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { useThemeMode } from '../composables/useTheme'

type Mermaid = typeof import('mermaid').default

const props = defineProps<{ code: string }>()
const host = ref<HTMLElement | null>(null)
const failed = ref('')
/** 主题切换要重渲染：mermaid 只吃 JS 常量读不到 CSS 变量（v0.16 补 v0.13 的遗留） */
const { mode } = useThemeMode()

let mermaid: Mermaid | null = null
let loading: Promise<Mermaid> | null = null
let seq = 0

/**
 * Mermaid 12 里 `flowchart-elk` 这个图类型会让它自己的 detector 把 config.layout 改写成 'elk'
 * （mermaid.core.mjs 全库唯一的 layout 赋值点），从而动态 import 那条 1.46 MB 的 elk 分支。
 * 我们已经固定 layout: 'dagre'，而 flowchart-elk 在 dagre 下的排版结果与 flowchart 完全一致，
 * 所以渲染前把首行的 `flowchart-elk` 收敛成 `flowchart` 即可：行为不变，但彻底切断 elk 下载路径。
 *
 * 只动首行的那一个单词，正文（节点定义、连线、缩进、注释）逐字保留——LLM 产出的结构不能被动过。
 * 正则与 mermaid detector 同锚点（^\s*），保证判断条件与它一致。
 */
function normalizeElk(code: string): string {
  if (!/^\s*flowchart-elk/.test(code)) return code
  return code.replace(/^(\s*)flowchart-elk/, '$1flowchart')
}

function themeVariables(dark: boolean) {
  // 与 theme.css 的 :root:root / :root:root.dark 保持同值：primaryColor=primary-light-9/-8，text=--vm-text，border/line=主色
  return dark
    ? { primaryColor: '#182c53', primaryTextColor: '#e5e7eb', primaryBorderColor: '#6f95e3', lineColor: '#6f95e3', fontSize: '13px' }
    : { primaryColor: '#eef3fd', primaryTextColor: '#1f2937', primaryBorderColor: '#3d6fd6', lineColor: '#3d6fd6', fontSize: '13px' }
}

async function getMermaid(): Promise<Mermaid> {
  if (mermaid) return mermaid
  if (!loading) {
    loading = import('mermaid').then((mod) => {
      mermaid = mod.default
      return mermaid
    })
  }
  try {
    return await loading
  } catch (err) {
    loading = null
    throw err
  }
}

async function render() {
  if (!host.value) return
  if (!props.code) {
    host.value.innerHTML = ''
    return
  }
  failed.value = ''
  try {
    const mm = await getMermaid()
    mm.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'base',
      // Mermaid 12 默认用 ELK，会多拉 1.5 MB 的布局块；产物里没有复杂布局需求，固定 dagre
      layout: 'dagre',
      themeVariables: themeVariables(mode.value === 'dark')
    })
    const out = await mm.render(`vm-diagram-${++seq}`, normalizeElk(props.code))
    host.value.innerHTML = out.svg
  } catch (err) {
    // LLM 生成的 mermaid 偶发语法错误，或按需加载失败；保留原文，不让整页崩
    failed.value = err instanceof Error ? err.message.slice(0, 180) : '渲染失败'
  }
}

onMounted(render)
watch(() => props.code, render)
watch(mode, render)
</script>

<template>
  <div class="wrap">
    <el-alert v-if="failed" :title="`Mermaid 草稿语法异常：${failed}`" type="warning" :closable="false" show-icon />
    <div ref="host" class="diagram" />
    <pre v-if="failed" class="raw">{{ code }}</pre>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; gap: 8px; }
.diagram { overflow: auto; background: var(--vm-surface, #fff); border: 1px solid var(--vm-border, #e6e8eb); border-radius: var(--vm-radius-sm, 6px); padding: 8px; min-height: 120px; }
.raw { font-size: 11px; color: var(--vm-muted, #5f6b7d); white-space: pre-wrap; margin: 0; }
</style>
