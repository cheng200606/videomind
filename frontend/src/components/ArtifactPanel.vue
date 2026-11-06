<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { ARTIFACT_LABEL, clock } from '../api/labels'
import type { ArtifactType, Item } from '../api/types'
import ConfidenceTag from './ConfidenceTag.vue'
import MermaidView from './MermaidView.vue'

const props = defineProps<{ items: Item[] }>()
const emit = defineEmits<{
  (e: 'select', item: Item): void
  (e: 'seek', ms: number): void
}>()

const TABS: { key: ArtifactType }[] = [
  { key: 'summary' }, { key: 'key_points' }, { key: 'uml_draft' }, { key: 'code_blocks' }
]
const active = ref<ArtifactType>('summary')

// 默认落在有内容的 tab；summary 未生成时不再先给用户一个空面板
watch(() => props.items, (items) => {
  if (!items.length) return
  if (items.some((i) => i.type === active.value)) return
  active.value = TABS.find((t) => items.some((i) => i.type === t.key))?.key ?? 'summary'
}, { immediate: true })

function of(kind: ArtifactType) {
  return props.items.filter((i) => i.type === kind)
}

/** UML 元素的锚点来自后端 payload.elements，点击即回证据时间点 */
const umlDrafts = computed(() => of('uml_draft'))
const umlElements = computed(() => umlDrafts.value.flatMap((uml) => {
  const raw = (uml.payload as { elements?: { id: string; label: string; anchor_ms: number }[] })?.elements ?? []
  return raw.map((e) => ({ ...e, key: `${uml.id}-${e.id}`, label: e.label || e.id }))
}))
const pitfalls = computed(() => of('key_points').filter((i) => (i.payload as { pitfall?: boolean }).pitfall))

/** F3 易错点过滤：只影响知识要点 tab 的可见列表 */
const onlyPitfall = ref(false)
const visiblePoints = computed(() =>
  onlyPitfall.value ? pitfalls.value : of('key_points')
)

function visible(kind: ArtifactType) {
  return kind === 'key_points' ? visiblePoints.value : of(kind)
}
</script>

<template>
  <el-tabs v-model="active" class="panel">
    <el-tab-pane
      v-for="t in TABS"
      :key="t.key"
      :name="t.key"
      :label="`${ARTIFACT_LABEL[t.key] ?? t.key} (${of(t.key).length})`"
      :lazy="t.key === 'uml_draft'"
    >
      <el-empty v-if="!of(t.key).length" description="该产物未生成（可在设置页「解析引擎」里调整默认产物集）" />

      <template v-else-if="t.key === 'uml_draft'">
        <div v-for="uml in umlDrafts" :key="uml.id" class="block">
          <MermaidView :code="uml.content" />
        </div>
        <div class="chips">
          <el-tag
            v-for="el in umlElements"
            :key="el.key"
            class="chip"
            type="info"
            role="button"
            tabindex="0"
            @click="emit('seek', el.anchor_ms)"
            @keydown.enter="emit('seek', el.anchor_ms)"
            @keydown.space.prevent="emit('seek', el.anchor_ms)"
          >{{ el.label }} · {{ clock(el.anchor_ms) }}</el-tag>
        </div>
      </template>

      <template v-else-if="t.key === 'code_blocks'">
        <div v-for="item in of(t.key)" :key="item.id" class="block">
          <div class="block-head">
            <span>{{ item.title }}</span>
            <el-link type="primary" @click="emit('seek', item.anchor_ms)">{{ clock(item.anchor_ms) }}</el-link>
          </div>
          <pre class="code">{{ item.content }}</pre>
        </div>
      </template>

      <template v-else>
        <div v-if="t.key === 'key_points'" class="pbar">
          <span v-if="pitfalls.length" class="pitfall-tip">
            ⚠ {{ pitfalls.length }} 条命中易错点（讲师反复强调 / 当场纠错 / 演示错误写法）
          </span>
          <el-checkbox v-model="onlyPitfall" size="small">只看易错点（F3）</el-checkbox>
        </div>
        <div v-if="visible(t.key).length" class="list">
          <div
            v-for="item in visible(t.key)" :key="item.id"
            class="list-item"
            role="button" tabindex="0"
            @click="emit('select', item)"
            @keydown.enter="emit('select', item)"
            @keydown.space.prevent="emit('select', item)"
          >
            <div class="line">
              <el-link type="primary" class="ts" @click.stop="emit('seek', item.anchor_ms)">{{ clock(item.anchor_ms) }}</el-link>
              <span class="txt">{{ item.content }}</span>
              <ConfidenceTag :confidence="item.confidence" />
            </div>
          </div>
        </div>
        <p v-else class="no-filter">没有符合筛选条件的条目</p>
      </template>
    </el-tab-pane>
  </el-tabs>
</template>

<style scoped>
.panel { height: 100%; }
.list { margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.list-item { padding: 8px 10px; border: 1px solid var(--vm-border, #e6e8eb); border-radius: 6px; background: #fff; cursor: pointer; }
.list-item:hover { border-color: var(--el-color-primary, #3d6fd6); }
.list-item:focus-visible { outline: 2px solid var(--el-color-primary, #3d6fd6); outline-offset: 1px; }
.line { display: flex; align-items: flex-start; gap: 8px; }
.ts { flex: none; font-variant-numeric: tabular-nums; }
.txt { flex: 1; line-height: 1.6; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.chip { cursor: pointer; }
.chip:focus-visible { outline: 2px solid var(--el-color-primary, #3d6fd6); outline-offset: 1px; }
.block { margin-bottom: 12px; }
.block-head { display: flex; justify-content: space-between; font-size: 13px; color: var(--vm-text-secondary, #4b5563); margin-bottom: 4px; }
.code { margin: 0; padding: 10px; background: var(--vm-code-bg, #12151c); color: #dbe1ea; border-radius: 6px; font-size: 12px; overflow: auto; }
.pbar { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.pitfall-tip { color: #b45309; font-size: 13px; }
.no-filter { margin: 8px 0; font-size: 13px; color: var(--vm-muted, #5f6b7d); }
</style>
