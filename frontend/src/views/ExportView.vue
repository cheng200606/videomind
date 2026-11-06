<script setup lang="ts">
import { MdPreview } from 'md-editor-v3'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { exportUrl, getBatch } from '../api/client'
import { STATUS_LABEL, STATUS_TYPE } from '../api/labels'
import type { BatchState } from '../api/types'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)

const batch = ref<BatchState | null>(null)
const md = ref('')
const loading = ref(true)
const error = ref('')

const isTerminal = computed(() =>
  ['succeeded', 'partial', 'failed'].includes(batch.value?.status ?? '')
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    batch.value = await getBatch(id)
    if (!isTerminal.value) {
      md.value = ''
      return
    }
    const resp = await fetch(exportUrl(id))
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`
      try {
        const body = await resp.json()
        if (body?.detail) detail = body.detail
      } catch { /* 非 JSON 错误体保持 HTTP 状态 */ }
      throw new Error(detail)
    }
    md.value = await resp.text()
  } catch (err) {
    // 不把错误文本当文稿渲染进预览
    md.value = ''
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function download() {
  if (!isTerminal.value || !md.value) return
  const blob = new Blob([md.value], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${batch.value?.name ?? 'videomind'}.md`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="export">
    <div class="crumb">
      <el-link @click="router.push('/')">视频库</el-link>
      <span>/</span>
      <el-link @click="router.push(`/batches/${id}`)">批次进度</el-link>
      <span>/</span><span>导出</span>
    </div>
    <div class="head">
      <div>
        <h2>批次文稿预览</h2>
        <p v-if="batch" class="sub">
          {{ batch.name }}
          <el-tag size="small" :type="STATUS_TYPE[batch.status] ?? 'info'">
            {{ STATUS_LABEL[batch.status] ?? batch.status }}
          </el-tag>
        </p>
      </div>
      <div class="actions">
        <el-button size="small" @click="load">重新生成</el-button>
        <el-button size="small" type="primary" :disabled="!isTerminal || loading" @click="download">下载 Markdown</el-button>
        <el-button size="small" @click="router.push(`/batches/${id}`)">返回批次</el-button>
      </div>
    </div>

    <el-alert
      v-if="!loading && !error && !isTerminal"
      type="warning"
      :closable="false"
      show-icon
      class="bar"
      title="批次尚未解析完成，导出暂不可用；请等待批次进入终态后再试。"
    />
    <el-alert
      v-else
      type="info"
      :closable="false"
      show-icon
      class="bar"
      title="导出的 UML 草稿为 Mermaid 源码，提交到 GitHub 后可原生渲染；/api/batches/{id}/structured 是给外部插件只读消费的结构化快照。"
    />

    <el-skeleton v-if="loading" :rows="12" animated />
    <el-alert v-else-if="error" type="error" :closable="false" show-icon :title="`文稿生成失败：${error}`">
      <el-button size="small" @click="router.push(`/batches/${id}`)">返回批次</el-button>
    </el-alert>
    <MdPreview v-else-if="isTerminal" :model-value="md" id="batch-preview" class="paper" />
  </div>
</template>

<style scoped>
.export { background: #fff; border: 1px solid var(--vm-border, #e6e8eb); border-radius: 8px; padding: 16px; }
.crumb { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 12px; color: var(--vm-muted, #5f6b7d); flex-wrap: wrap; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.head h2 { margin: 0; font-size: 18px; }
.sub { margin: 4px 0 0; color: var(--vm-muted, #5f6b7d); font-size: 13px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.bar { margin-bottom: 12px; }
.paper { max-width: 900px; margin: 0 auto; }
</style>
