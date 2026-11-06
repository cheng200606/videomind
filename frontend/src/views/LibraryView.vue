<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { deleteBatch, listTags, search } from '../api/client'
import { ARTIFACT_LABEL, STATUS_LABEL, STATUS_TYPE, clock, fmtDateTime } from '../api/labels'
import type { BatchSummary, Item, TagInfo } from '../api/types'
import { useBatchStore } from '../stores/batch'
import ConfidenceTag from '../components/ConfidenceTag.vue'

const store = useBatchStore()
const router = useRouter()
const loading = ref(true)
const loadError = ref('')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    await Promise.all([
      store.refreshList(),
      listTags().then((t) => { tags.value = t })
    ])
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)

/** B6 跨视频检索：标签过滤 + 关键词 + 置信度，不是语义检索（产品定义 §九 诚实边界） */
const tags = ref<TagInfo[]>([])
const tagId = ref<number | undefined>()
const keyword = ref('')
const conf = ref<string | undefined>()
const results = ref<Item[]>([])
const searched = ref(false)
const searching = ref(false)
const searchError = ref('')
const expanded = ref<string[]>([])

async function runSearch() {
  searching.value = true
  searchError.value = ''
  try {
    results.value = await search({ tag: tagId.value, q: keyword.value.trim() || undefined, confidence: conf.value || undefined })
    searched.value = true
  } catch (err) {
    results.value = []
    searched.value = true
    searchError.value = err instanceof Error ? err.message : String(err)
  } finally {
    searching.value = false
  }
}

/** 删除只清运行时数据（后端级联），解析中的批次按钮已禁用 */
async function removeBatch(b: BatchSummary) {
  try {
    await ElMessageBox.confirm(`删除批次「${b.name}」？解析产物与上传文件将一并清除。`, '删除批次', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await deleteBatch(b.id)
    ElMessage.success('批次已删除')
    await store.refreshList()
  } catch (err) {
    ElMessage.error(`删除失败：${err instanceof Error ? err.message : err}`)
  }
}
</script>

<template>
  <div>
    <div class="head">
      <h2>视频库</h2>
      <el-button type="primary" @click="router.push('/upload')">新建批次</el-button>
    </div>

    <el-collapse v-model="expanded" class="search">
      <el-collapse-item name="on" title="跨视频检索 · 按标签 + 关键词定位条目（标签过滤，不是语义检索）">
        <div class="srow">
          <el-select v-model="tagId" clearable placeholder="按标签过滤" class="sel">
            <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <el-select v-model="conf" clearable placeholder="置信度（F4）" class="cfd">
            <el-option label="明述" value="explicit" />
            <el-option label="推断" value="inferred" />
            <el-option label="低置信" value="low" />
          </el-select>
          <el-input v-model="keyword" clearable placeholder="关键词，如 ref / 生命周期" class="kw" @keyup.enter="runSearch" />
          <el-button type="primary" :loading="searching" @click="runSearch">检索</el-button>
        </div>
        <el-alert v-if="searchError" type="error" :closable="false" show-icon class="search-err" :title="`检索失败：${searchError}`" />
        <el-table
          v-if="results.length"
          :data="results"
          size="small"
          class="rt"
          @row-click="(r: Item) => router.push({ name: 'workbench', params: { id: r.video_id }, query: { item: String(r.id) } })"
        >
          <el-table-column prop="title" label="条目" min-width="220" />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">{{ ARTIFACT_LABEL[row.type as string] ?? row.type }}</template>
          </el-table-column>
          <el-table-column label="置信度" width="96">
            <template #default="{ row }"><ConfidenceTag :confidence="row.confidence" /></template>
          </el-table-column>
          <el-table-column prop="video_name" label="所属视频" min-width="150" />
          <el-table-column label="锚点" width="84">
            <template #default="{ row }">{{ clock(row.anchor_ms) }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="searched" description="没有匹配的条目" :image-size="60" />
      </el-collapse-item>
    </el-collapse>

    <el-skeleton v-if="loading" :rows="4" animated />
    <el-alert v-else-if="loadError" type="error" :closable="false" show-icon :title="`视频库加载失败：${loadError}`">
      <el-button size="small" @click="load">重试</el-button>
    </el-alert>
    <el-empty v-else-if="!store.batches.length" description="还没有批次，先去批量上传几条本地视频" />

    <div v-else class="grid">
      <el-card v-for="b in store.batches" :key="b.id" class="card" shadow="hover">
        <div class="name">{{ b.name }}</div>
        <div class="line">
          <el-tag size="small" :type="STATUS_TYPE[b.status] ?? 'info'">{{ STATUS_LABEL[b.status] ?? b.status }}</el-tag>
          <span>{{ b.video_count }} 条</span>
        </div>
        <div class="line muted">{{ fmtDateTime(b.created_at) }}</div>
        <div class="acts">
          <el-button size="small" @click="router.push(`/batches/${b.id}`)">解析进度</el-button>
          <el-button
            size="small"
            :disabled="!['succeeded', 'partial', 'failed'].includes(b.status)"
            @click="router.push(`/batches/${b.id}/export`)"
          >导出文稿</el-button>
          <el-button size="small" type="danger" plain :disabled="['pending', 'running'].includes(b.status)" @click="removeBatch(b)">
            删除
          </el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; gap: 10px; flex-wrap: wrap; }
.head h2 { margin: 0; }
.search { margin-bottom: 16px; }
.srow { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.sel { width: 200px; max-width: 100%; }
.cfd { width: 130px; max-width: 100%; }
.kw { width: 260px; max-width: 100%; }
.search-err { margin-bottom: 10px; }
.rt :deep(tbody tr) { cursor: pointer; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.card .name { font-weight: 600; margin-bottom: 8px; }
.line { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; }
.muted { color: var(--vm-muted, #5f6b7d); }
.acts { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
</style>
