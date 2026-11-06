<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

type Mermaid = typeof import('mermaid').default

const props = defineProps<{ code: string }>()
const host = ref<HTMLElement | null>(null)
const failed = ref('')

let mermaid: Mermaid | null = null
let loading: Promise<Mermaid> | null = null
let seq = 0

async function getMermaid(): Promise<Mermaid> {
  if (mermaid) return mermaid
  if (!loading) {
    loading = import('mermaid').then((mod) => {
      const instance = mod.default
      instance.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'base',
        // Mermaid 12 默认用 ELK，会多拉 1.5 MB 的布局块；产物里没有复杂布局需求，固定 dagre
        layout: 'dagre',
        themeVariables: {
          primaryColor: '#eef3fd',
          primaryTextColor: '#1f2937',
          primaryBorderColor: '#3d6fd6',
          lineColor: '#3d6fd6',
          fontSize: '13px'
        }
      })
      mermaid = instance
      return instance
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
    const out = await mm.render(`vm-diagram-${++seq}`, props.code)
    host.value.innerHTML = out.svg
  } catch (err) {
    // LLM 生成的 mermaid 偶发语法错误，或按需加载失败；保留原文，不让整页崩
    failed.value = err instanceof Error ? err.message.slice(0, 180) : '渲染失败'
  }
}

onMounted(render)
watch(() => props.code, render)
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
.diagram { overflow: auto; background: #fff; border: 1px solid var(--vm-border, #e6e8eb); border-radius: 6px; padding: 8px; min-height: 120px; }
.raw { font-size: 11px; color: var(--vm-muted, #5f6b7d); white-space: pre-wrap; margin: 0; }
</style>
