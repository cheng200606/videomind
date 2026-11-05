<script setup lang="ts">
import { MdPreview } from 'md-editor-v3'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { exportUrl } from '../api/client'

const route = useRoute()
const id = Number(route.params.id)

const md = ref('')
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetch(exportUrl(id))
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
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
</script>

<template>
  <div class="export">
    <div class="head">
      <h2>批次文稿预览</h2>
      <div>
        <el-button size="small" @click="load">重新生成</el-button>
        <el-button size="small" type="primary" tag="a" :href="exportUrl(id)">下载 Markdown</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="bar"
      title="导出的 UML 草稿为 Mermaid 源码，提交到 GitHub 后可原生渲染；/api/batches/{id}/structured 是给外部插件只读消费的结构化快照。" />

    <el-skeleton v-if="loading" :rows="12" animated />
    <el-alert v-else-if="error" type="error" :closable="false" show-icon :title="`文稿生成失败：${error}`" />
    <MdPreview v-else :model-value="md" id="batch-preview" class="paper" />
  </div>
</template>

<style scoped>
.export { background: #fff; border: 1px solid #e6e8eb; border-radius: 8px; padding: 16px; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.head h2 { margin: 0; font-size: 18px; }
.bar { margin-bottom: 12px; }
.paper { max-width: 900px; margin: 0 auto; }
</style>
