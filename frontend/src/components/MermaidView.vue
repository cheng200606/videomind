<script setup lang="ts">
import mermaid from 'mermaid'
import { onMounted, ref, watch } from 'vue'

const props = defineProps<{ code: string }>()
const host = ref<HTMLElement | null>(null)
const failed = ref('')

mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'default' })

let seq = 0

async function render() {
  if (!host.value) return
  if (!props.code) {
    host.value.innerHTML = ''
    return
  }
  failed.value = ''
  try {
    const out = await mermaid.render(`vm-diagram-${++seq}`, props.code)
    host.value.innerHTML = out.svg
  } catch (err) {
    // LLM 生成的 mermaid 偶尔语法不合法；这里保留原文，不让整页崩
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
.diagram { overflow: auto; background: #fff; border: 1px solid #e6e8eb; border-radius: 6px; padding: 8px; min-height: 120px; }
.raw { font-size: 11px; color: #8b95a7; white-space: pre-wrap; margin: 0; }
</style>
