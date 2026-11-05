<script setup lang="ts">
import { computed, ref } from 'vue'

import type { ArtifactType, Item } from '../api/types'
import ConfidenceTag from './ConfidenceTag.vue'
import MermaidView from './MermaidView.vue'

const props = defineProps<{ items: Item[] }>()
const emit = defineEmits<{
  (e: 'select', item: Item): void
  (e: 'seek', ms: number): void
}>()

const TABS: { key: ArtifactType; label: string }[] = [
  { key: 'summary', label: '内容总结' },
  { key: 'key_points', label: '知识要点' },
  { key: 'uml_draft', label: 'UML 草稿' },
  { key: 'code_blocks', label: '代码块' }
]
const active = ref<ArtifactType>('summary')

function of(kind: ArtifactType) {
  return props.items.filter((i) => i.type === kind)
}

/** UML 元素的锚点来自后端 payload.elements，点击即回证据时间点 */
const umlElements = computed(() => {
  const uml = of('uml_draft')[0]
  const raw = (uml?.payload as { elements?: { id: string; label: string; anchor_ms: number }[] })?.elements ?? []
  return raw.map((e) => ({ ...e, label: e.label || e.id }))
})
const pitfalls = computed(() => of('key_points').filter((i) => (i.payload as { pitfall?: boolean }).pitfall))

/** F3 易错点过滤：只影响知识要点 tab 的可见列表 */
const onlyPitfall = ref(false)
const visiblePoints = computed(() =>
  onlyPitfall.value ? pitfalls.value : of('key_points')
)

function visible(kind: ArtifactType) {
  return kind === 'key_points' ? visiblePoints.value : of(kind)
}

function clock(ms: number) {
  const total = Math.floor(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}
</script>

<template>
  <el-tabs v-model="active" class="panel">
    <el-tab-pane v-for="t in TABS" :key="t.key" :name="t.key" :label="`${t.label} (${of(t.key).length})`">
      <el-empty v-if="!of(t.key).length" description="该产物未生成（可在上传页「解析参数」里切换默认产物集）" />

      <template v-else-if="t.key === 'uml_draft'">
        <MermaidView :code="of(t.key)[0].content" />
        <div class="chips">
          <el-tag
            v-for="el in umlElements"
            :key="el.id"
            class="chip"
            type="info"
            @click="emit('seek', el.anchor_ms)"
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
        <ul v-if="visible(t.key).length" class="list">
          <li v-for="item in visible(t.key)" :key="item.id" @click="emit('select', item)">
            <div class="line">
              <el-link type="primary" class="ts" @click.stop="emit('seek', item.anchor_ms)">{{ clock(item.anchor_ms) }}</el-link>
              <span class="txt">{{ item.content }}</span>
              <ConfidenceTag :confidence="item.confidence" />
            </div>
          </li>
        </ul>
        <p v-else class="no-filter">没有符合筛选条件的条目</p>
      </template>
    </el-tab-pane>
  </el-tabs>
</template>

<style scoped>
.panel { height: 100%; }
.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.list li { padding: 8px 10px; border: 1px solid #e6e8eb; border-radius: 6px; background: #fff; cursor: pointer; }
.list li:hover { border-color: #3d6fd6; }
.line { display: flex; align-items: flex-start; gap: 8px; }
.ts { flex: none; font-variant-numeric: tabular-nums; }
.txt { flex: 1; line-height: 1.6; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.chip { cursor: pointer; }
.block { margin-bottom: 12px; }
.block-head { display: flex; justify-content: space-between; font-size: 13px; color: #606a7b; margin-bottom: 4px; }
.code { margin: 0; padding: 10px; background: #12151c; color: #dbe1ea; border-radius: 6px; font-size: 12px; overflow: auto; }
.pbar { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.pitfall-tip { color: #b45309; font-size: 13px; }
.no-filter { margin: 8px 0; font-size: 13px; color: #8b95a7; }
</style>
