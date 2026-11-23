<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { listTags, search } from '../api/client'
import { highlightSegments, matchSnippet } from '../api/highlight'
import { ARTIFACT_LABEL, clock } from '../api/labels'
import type { Item, TagInfo } from '../api/types'
import ConfidenceTag from './ConfidenceTag.vue'

const router = useRouter()

/** B6 跨视频检索：标签过滤 + 关键词 + 置信度，不是语义检索（产品定义 §九 诚实边界） */
const SEARCH_LIMIT = 200
const tags = ref<TagInfo[]>([])
const tagId = ref<number | undefined>()
const keyword = ref('')
const conf = ref<string | undefined>()
const results = ref<Item[]>([])
const total = ref(0)
const searched = ref(false)
const searching = ref(false)
const searchError = ref('')
/** 高亮用「已提交的关键词」而非输入框实时值：条件改了但未重新检索时，旧结果高亮不乱跳 */
const lastQuery = ref('')

/** 空条件等于「浏览全库」，随数据量变慢且误导：至少要给一个条件才允许检索 */
const hasCriteria = computed(() => tagId.value !== undefined || !!keyword.value.trim() || !!conf.value)
const clipped = computed(() => total.value > results.value.length)

function segments(text: string) {
  return highlightSegments(text, lastQuery.value)
}

function snippet(text: string) {
  return highlightSegments(matchSnippet(text, lastQuery.value), lastQuery.value)
}

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
  if (!hasCriteria.value) return
  searching.value = true
  searchError.value = ''
  try {
    const resp = await search({ tag: tagId.value, q: keyword.value.trim() || undefined, confidence: conf.value || undefined })
    results.value = resp.items
    total.value = resp.total
    searched.value = true
    lastQuery.value = keyword.value.trim()
  } catch (err) {
    results.value = []
    total.value = 0
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
      <el-tooltip content="至少提供标签 / 关键词 / 置信度之一" :disabled="hasCriteria" placement="top">
        <span>
          <el-button type="primary" :loading="searching" :disabled="!hasCriteria" @click="runSearch">检索</el-button>
        </span>
      </el-tooltip>
    </div>
    <p v-if="!searched && !hasCriteria" class="hint">按标签、置信度或关键词跨视频定位条目——标签过滤，不是语义检索。</p>
    <el-alert v-if="searchError" type="error" :closable="false" show-icon class="search-err" :title="`检索失败：${searchError}`" />
    <template v-if="results.length">
      <p class="total vm-num">
        共 {{ total }} 条<template v-if="clipped">，已显示前 {{ SEARCH_LIMIT }} 条，请缩小条件</template>
        <template v-if="lastQuery">· 按相关度排序（标题命中优先）</template>
      </p>
      <el-table
        :data="results"
        size="small"
        class="rt"
        @row-click="(r: Item) => router.push({ name: 'workbench', params: { id: r.video_id }, query: { item: String(r.id) } })"
      >
        <el-table-column label="条目" min-width="220">
          <template #default="{ row }">
            <span class="tcell">
              <template v-for="(s, i) in segments(row.title)" :key="i"
                ><mark v-if="s.hit" class="hl">{{ s.text }}</mark
                ><template v-else>{{ s.text }}</template></template>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="260">
          <template #default="{ row }">
            <span class="tcell snip">
              <template v-for="(s, i) in snippet(row.content)" :key="i"
                ><mark v-if="s.hit" class="hl">{{ s.text }}</mark
                ><template v-else>{{ s.text }}</template></template>
            </span>
          </template>
        </el-table-column>
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
    </template>
    <el-empty v-else-if="searched && !searchError" description="没有匹配的条目" :image-size="60" />
  </div>
</template>

<style scoped>
.srow { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.sel { width: 200px; max-width: 100%; }
.cfd { width: 130px; max-width: 100%; }
.kw { width: 260px; max-width: 100%; }
.search-err { margin-bottom: 10px; }
.hint { margin: 0 0 10px; font-size: 12px; color: var(--vm-muted, #5f6b7d); }
.total { margin: 4px 0 8px; font-size: 12px; color: var(--vm-muted, #5f6b7d); }
.rt :deep(tbody tr) { cursor: pointer; }
.tcell { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.snip { color: var(--vm-text-secondary, #4b5563); font-size: 12px; }
.hl { background: var(--vm-hit-bg, #fde68a); color: inherit; border-radius: 2px; padding: 0 1px; }
</style>
