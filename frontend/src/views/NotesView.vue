<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { MdEditor } from 'md-editor-v3'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { addNote, getItem, revise, updateNote } from '../api/client'
import { EDITOR_LABEL, REVISION_LABEL, REVISION_TRANSITIONS, REVISION_TYPE, clock, fmtDateTime } from '../api/labels'
import type { ItemDetail, RevisionState } from '../api/types'
import ConfidenceTag from '../components/ConfidenceTag.vue'

const route = useRoute()
const router = useRouter()
const itemId = Number(route.params.id)

const detail = ref<ItemDetail | null>(null)
const noteId = ref<number | null>(null)
const noteCount = ref(0)
const draft = ref('')
const busy = ref(false)

const state = computed(() => detail.value?.revisions.at(-1)?.state ?? 'draft')
const FLOW: { state: RevisionState; label: string }[] = [
  { state: 'pending_confirm', label: '提交待确认' },
  { state: 'confirmed', label: '确认' },
  { state: 'revised', label: '标记已修订' },
  { state: 'draft', label: '退回草稿' }
]

/** 非法跳转按钮直接禁用，不再点了之后靠后端 422 弹错 */
function allowed(next: RevisionState): boolean {
  return (REVISION_TRANSITIONS[state.value] ?? []).includes(next)
}

const loadError = ref('')

async function load() {
  loadError.value = ''
  try {
    const data = await getItem(itemId)
    detail.value = data
    // 深链可指定 note；否则编辑最新一条（后端已按 id 排序）
    const wanted = Number(route.query.note)
    const note = data.notes.find((n) => n.id === wanted) ?? data.notes.at(-1)
    noteId.value = note?.id ?? null
    draft.value = note?.content ?? ''
    noteCount.value = data.notes.length
  } catch (err) {
    // 直达 URL / 条目被随批次删除时不再永远骨架屏
    loadError.value = err instanceof Error ? err.message : '条目加载失败'
  }
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
  <div v-if="detail">
    <div class="crumb">
      <el-link @click="router.push('/')">视频库</el-link>
      <span>/</span>
      <el-link @click="router.push(`/videos/${detail.video_id}`)">知识工作台</el-link>
      <span>/</span><span>笔记</span>
    </div>
    <div class="notes">
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
      <el-alert
        v-if="noteCount > 1"
        type="info"
        :closable="false"
        show-icon
        class="multi"
        :title="`该条目有 ${noteCount} 条笔记，当前编辑最新一条；保存不会合并历史笔记。`"
      />
      <MdEditor v-model="draft" :toolbars-exclude="['github', 'save', 'prettier']" />
      <el-button type="primary" :loading="busy" @click="save">保存笔记</el-button>
      <p class="muted">笔记绑定条目时间点，支持从笔记跳回原片（用例「笔记与时间锚点」）。</p>
    </el-card>

    <el-card class="history" shadow="never">
      <template #header><b>讲义状态与版本记录</b></template>
      <div class="state">
        当前：<el-tag size="small" :type="REVISION_TYPE[state] ?? 'info'">{{ REVISION_LABEL[state] ?? state }}</el-tag>
        <div class="flows">
          <el-button
            v-for="f in FLOW" :key="f.state" size="small"
            :disabled="!allowed(f.state)" @click="move(f.state)"
          >{{ f.label }}</el-button>
        </div>
      </div>
      <el-timeline class="tl">
        <el-timeline-item v-for="r in detail.revisions" :key="r.id" :timestamp="fmtDateTime(r.edited_at)" placement="top">
          <div>{{ REVISION_LABEL[r.state] ?? r.state }} · {{ EDITOR_LABEL[r.editor] ?? r.editor }}</div>
          <div class="snap">{{ r.snapshot.slice(0, 60) }}{{ r.snapshot.length > 60 ? '…' : '' }}</div>
        </el-timeline-item>
      </el-timeline>
    </el-card>
    </div>
  </div>
  <el-alert v-else-if="loadError" type="error" :closable="false" show-icon :title="`笔记加载失败：${loadError}`">
    <el-button size="small" @click="router.push('/')">返回视频库</el-button>
  </el-alert>
  <el-skeleton v-else :rows="8" animated />
</template>

<style scoped>
.crumb { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 12px; color: var(--vm-muted, #5f6b7d); flex-wrap: wrap; }
.notes { display: grid; grid-template-columns: 320px minmax(420px, 1fr) 280px; gap: 14px; align-items: start; }
@media (max-width: 1080px) {
  .notes { grid-template-columns: 1fr; }
}
.row { display: flex; align-items: center; gap: 8px; }
.ts { color: var(--el-color-primary, #3d6fd6); font-size: 12px; }
.title { margin: 8px 0; font-size: 15px; }
.content { line-height: 1.7; font-size: 13px; }
.quote { margin: 0; padding: 8px 10px; background: var(--vm-quote-bg, #f6f7f9); border-left: 3px solid var(--el-color-primary, #3d6fd6); font-size: 12px; }
.conflict { color: #b45309; font-size: 12px; }
.anchor-btn { float: right; }
.multi { margin-bottom: 10px; }
.editor :deep(.md-editor-toolbar-wrapper) { height: auto; }
.editor :deep(.md-editor-toolbar) { flex-wrap: wrap; }
.state { font-size: 13px; margin-bottom: 12px; }
.flows { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.tl { margin-top: 14px; }
.snap { font-size: 12px; color: var(--vm-text-secondary, #4b5563); }
.muted { color: var(--vm-muted, #5f6b7d); font-size: 12px; }
</style>
