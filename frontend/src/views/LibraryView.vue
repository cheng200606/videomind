<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { listTags, search } from '../api/client'
import type { Item, TagInfo } from '../api/types'
import { useBatchStore } from '../stores/batch'
import ConfidenceTag from '../components/ConfidenceTag.vue'

const store = useBatchStore()
const router = useRouter()
onMounted(() => {
  void store.refreshList()
  void listTags().then((t) => (tags.value = t))
})

/** B6 跨视频检索：标签过滤 + 关键词 + 置信度，不是语义检索（产品定义 §九 诚实边界） */
const tags = ref<TagInfo[]>([])
const tagId = ref<number | undefined>()
const keyword = ref('')
const conf = ref<string | undefined>()
const results = ref<Item[]>([])
const searched = ref(false)
const searching = ref(false)
const expanded = ref<string[]>([])

async function runSearch() {
  searching.value = true
  try {
    results.value = await search({ tag: tagId.value, q: keyword.value.trim() || undefined, confidence: conf.value || undefined })
    searched.value = true
  } finally {
    searching.value = false
  }
}

function clock(ms: number) {
  const total = Math.floor(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
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
        <el-table
          v-if="results.length"
          :data="results"
          size="small"
          class="rt"
          @row-click="(r: Item) => router.push(`/videos/${r.video_id}`)"
        >
          <el-table-column prop="title" label="条目" min-width="220" />
          <el-table-column prop="type" label="类型" width="110" />
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

    <el-empty v-if="!store.batches.length" description="还没有批次，先去批量上传几条本地视频" />

    <div class="grid">
      <el-card v-for="b in store.batches" :key="b.id" class="card" shadow="hover">
        <div class="name">{{ b.name }}</div>
        <div class="line">
          <el-tag size="small" :type="b.status === 'succeeded' ? 'success' : b.status === 'failed' ? 'danger' : 'info'">
            {{ b.status }}
          </el-tag>
          <span>{{ b.video_count }} 条</span>
        </div>
        <div class="line muted">{{ new Date(b.created_at).toLocaleString() }}</div>
        <div class="acts">
          <el-button size="small" @click="router.push(`/batches/${b.id}`)">解析进度</el-button>
          <el-button size="small" @click="router.push(`/batches/${b.id}/export`)">导出文稿</el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.head h2 { margin: 0; }
.search { margin-bottom: 16px; }
.srow { display: flex; gap: 8px; margin-bottom: 10px; }
.sel { width: 200px; }
.cfd { width: 130px; }
.kw { width: 260px; }
.rt :deep(tbody tr) { cursor: pointer; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.card .name { font-weight: 600; margin-bottom: 8px; }
.line { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; }
.muted { color: #8b95a7; }
.acts { display: flex; gap: 8px; margin-top: 10px; }
</style>
