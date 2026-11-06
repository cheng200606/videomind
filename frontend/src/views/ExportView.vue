<script setup lang="ts">
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { exportUrl, getBatch } from '../api/client'
import { STATUS_LABEL, STATUS_TYPE } from '../api/labels'
import type { BatchState } from '../api/types'
import PageHeader from '../components/PageHeader.vue'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))

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
    batch.value = await getBatch(id.value)
    if (!isTerminal.value) {
      md.value = ''
      return
    }
    const resp = await fetch(exportUrl(id.value))
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
watch(() => route.params.id, () => void load(), { immediate: true })

function download() {
  if (!isTerminal.value || !md.value) return
  const blob = new Blob([md.value], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${batch.value?.name ?? 'videomind'}.md`
  a.click()
  // 立即 revoke 在部分浏览器上会让下载中断
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>

<template>
  <div>
    <PageHeader
      title="导出文稿"
      :crumbs="[{ label: '视频库', to: '/' }, { label: batch?.name ?? '批次进度', to: `/batches/${id}` }]"
    >
      <template #tag>
        <el-tag v-if="batch" size="small" :type="STATUS_TYPE[batch.status] ?? 'info'">
          {{ STATUS_LABEL[batch.status] ?? batch.status }}
        </el-tag>
      </template>
      <template #actions>
        <el-button size="small" @click="load">重新生成</el-button>
        <el-button size="small" type="primary" :disabled="!isTerminal || loading" @click="download">下载 Markdown</el-button>
      </template>
    </PageHeader>

    <el-alert
      v-if="!loading && !error && !isTerminal"
      type="warning"
      :closable="false"
      show-icon
      class="bar"
      title="批次尚未解析完成，导出暂不可用"
      description="请等待批次进入终态后再试。"
    />
    <el-alert
      v-else-if="!loading && !error"
      type="info"
      :closable="false"
      show-icon
      class="bar"
      title="导出的 UML 草稿为 Mermaid 源码，提交到 GitHub 后可原生渲染"
      description="/api/batches/{id}/structured 是给外部插件只读消费的结构化快照。"
    />

    <div class="export vm-card">
      <el-skeleton v-if="loading" :rows="12" animated />
      <el-alert v-else-if="error" type="error" :closable="false" show-icon :title="`文稿生成失败：${error}`">
        <el-button size="small" @click="router.push(`/batches/${id}`)">返回批次</el-button>
      </el-alert>
      <MdPreview v-else-if="isTerminal" :model-value="md" id="batch-preview" class="paper" />
    </div>
  </div>
</template>

<style scoped>
.export { padding: 16px; }
.bar { margin-bottom: 12px; }
.paper { max-width: 900px; margin: 0 auto; }
</style>
