<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { MdEditor } from 'md-editor-v3'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { addNote, getItem, revise, updateNote } from '../api/client'
import type { ItemDetail, RevisionState } from '../api/types'
import ConfidenceTag from '../components/ConfidenceTag.vue'

const route = useRoute()
const itemId = Number(route.params.id)

const detail = ref<ItemDetail | null>(null)
const noteId = ref<number | null>(null)
const draft = ref('')
const busy = ref(false)

const state = computed(() => detail.value?.revisions.at(-1)?.state ?? 'draft')
const FLOW: { state: RevisionState; label: string }[] = [
  { state: 'pending_confirm', label: '提交待确认' },
  { state: 'confirmed', label: '确认' },
  { state: 'revised', label: '标记已修订' },
  { state: 'draft', label: '退回草稿' }
]

function clock(ms: number) {
  const total = Math.floor(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

async function load() {
  const data = await getItem(itemId)
  detail.value = data
  const note = data.notes[0]
  noteId.value = note?.id ?? null
  draft.value = note?.content ?? ''
}
onMounted(load)

async function save() {
  const anchor = detail.value?.anchor_ms ?? 0
  busy.value = true
  try {
    if (noteId.value === null) {
      const { id } = await addNote(itemId, draft.value, anchor)
      noteId.value = id
    } else {
      await updateNote(noteId.value, draft.value, anchor)
    }
    ElMessage.success('笔记已保存')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    busy.value = false
  }
}

/** 讲义修订状态机（图 7 右半）：非法跳转由后端拒绝，这里只如实报错 */
async function move(next: RevisionState) {
  try {
    await revise(itemId, next)
    await load()
  } catch (err) {
    ElMessage.error(`状态机拒绝：${err instanceof Error ? err.message : err}`)
  }
}

function insertAnchor() {
  if (!detail.value) return
  draft.value += `\n> 锚点 \`[${clock(detail.value.anchor_ms)}]\` ${detail.value.title}\n`
}
</script>

<template>
  <div v-if="detail" class="notes">
    <el-card class="src" shadow="never">
      <template #header><b>来源条目</b></template>
      <div class="row">
        <ConfidenceTag :confidence="detail.confidence" />
        <span class="ts">{{ clock(detail.anchor_ms) }}</span>
        <span class="muted">{{ detail.video_name }}</span>
      </div>
      <h3 class="title">{{ detail.title }}</h3>
      <p class="content">{{ detail.content }}</p>
      <blockquote v-if="detail.evidence" class="quote">{{ detail.evidence.quote }}</blockquote>
      <p v-if="detail.conflicts.length" class="conflict">⚠ 一致性提示：{{ detail.conflicts[0].description }}</p>
    </el-card>

    <el-card class="editor" shadow="never">
      <template #header>
        <b>笔记</b>
        <el-button size="small" class="anchor-btn" @click="insertAnchor">插入时间锚点</el-button>
      </template>
      <MdEditor v-model="draft" :toolbars-exclude="['github', 'save', 'prettier']" />
      <el-button type="primary" :loading="busy" @click="save">保存笔记</el-button>
      <p class="muted">笔记绑定条目时间点，支持从笔记跳回原片（用例「笔记与时间锚点」）。</p>
    </el-card>

    <el-card class="history" shadow="never">
      <template #header><b>讲义状态与版本记录</b></template>
      <div class="state">
        当前：<el-tag size="small">{{ state }}</el-tag>
        <div class="flows">
          <el-button v-for="f in FLOW" :key="f.state" size="small" @click="move(f.state)">{{ f.label }}</el-button>
        </div>
      </div>
      <el-timeline class="tl">
        <el-timeline-item v-for="r in detail.revisions" :key="r.id" :timestamp="r.edited_at.slice(0, 16)" placement="top">
          <div>{{ r.state }} · {{ r.editor }}</div>
          <div class="snap">{{ r.snapshot.slice(0, 60) }}{{ r.snapshot.length > 60 ? '…' : '' }}</div>
        </el-timeline-item>
      </el-timeline>
    </el-card>
  </div>
  <el-skeleton v-else :rows="8" animated />
</template>

<style scoped>
.notes { display: grid; grid-template-columns: 320px minmax(420px, 1fr) 280px; gap: 14px; align-items: start; }
.row { display: flex; align-items: center; gap: 8px; }
.ts { color: #3d6fd6; font-size: 12px; }
.title { margin: 8px 0; font-size: 15px; }
.content { line-height: 1.7; font-size: 13px; }
.quote { margin: 0; padding: 8px 10px; background: #f6f7f9; border-left: 3px solid #3d6fd6; font-size: 12px; }
.conflict { color: #b45309; font-size: 12px; }
.anchor-btn { float: right; }
.state { font-size: 13px; margin-bottom: 12px; }
.flows { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.tl { margin-top: 14px; }
.snap { font-size: 12px; color: #606a7b; }
.muted { color: #a5adba; font-size: 12px; }
</style>
