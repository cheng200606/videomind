<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { listTags, search } from '../api/client'
import { ARTIFACT_LABEL, clock } from '../api/labels'
import type { Item, TagInfo } from '../api/types'
import ConfidenceTag from './ConfidenceTag.vue'

const router = useRouter()

/** B6 跨视频检索：标签过滤 + 关键词 + 置信度，不是语义检索（产品定义 §九 诚实边界） */
const tags = ref<TagInfo[]>([])
const tagId = ref<number | undefined>()
const keyword = ref('')
const conf = ref<string | undefined>()
const results = ref<Item[]>([])
const searched = ref(false)
const searching = ref(false)
const searchError = ref('')

// 条件变了就收起上次的“无结果”提示，避免用户以为新条件也没有结果
watch([tagId, keyword, conf], () => { searched.value = false })

onMounted(async () => {
  try {
    tags.value = await listTags()
  } catch {
    tags.value = []
  }
})

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
</script>

<template>
  <div>
    <div class="srow">
      <el-select v-model="tagId" clearable filterable placeholder="按标签过滤（含视频级）" class="sel" aria-label="按标签过滤">
        <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
      </el-select>
      <el-select v-model="conf" clearable placeholder="置信度（F4）" class="cfd" aria-label="按置信度过滤">
        <el-option label="明述" value="explicit" />
        <el-option label="推断" value="inferred" />
        <el-option label="低置信" value="low" />
      </el-select>
      <el-input v-model="keyword" clearable placeholder="关键词，如 ref / 生命周期" class="kw" aria-label="检索关键词" @keyup.enter="runSearch" />
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
        <template #default="{ row }"><span class="vm-ts">{{ clock(row.anchor_ms) }}</span></template>
      </el-table-column>
    </el-table>
    <el-empty v-else-if="searched && !searchError" description="没有匹配的条目" :image-size="60" />
  </div>
</template>

<style scoped>
.srow { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.sel { width: 200px; max-width: 100%; }
.cfd { width: 130px; max-width: 100%; }
.kw { width: 260px; max-width: 100%; }
.search-err { margin-bottom: 10px; }
.rt :deep(tbody tr) { cursor: pointer; }
</style>
