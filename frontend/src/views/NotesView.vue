<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { MdEditor } from 'md-editor-v3'
import 'md-editor-v3/lib/style.css'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { addNote, getItem, revise, updateNote } from '../api/client'
import { EDITOR_LABEL, REVISION_LABEL, REVISION_TRANSITIONS, REVISION_TYPE, clock, fmtDateTime } from '../api/labels'
import type { ItemDetail, RevisionState } from '../api/types'
import ConfidenceTag from '../components/ConfidenceTag.vue'
import { useLeaveGuard } from '../composables/useLeaveGuard'

const route = useRoute()
const router = useRouter()
const itemId = computed(() => Number(route.params.id))

const detail = ref<ItemDetail | null>(null)
const noteId = ref<number | null>(null)
const noteDraft = ref('')
const lectureDraft = ref('')
const editorTab = ref<'note' | 'lecture'>('note')

/** md-editor 的 CodeMirror 没有可访问名称，按当前 Tab 给编辑区补 aria-label */
function labelEditors() {
  const apply = () => {
    document.querySelectorAll<HTMLElement>('.md-editor .cm-content').forEach((el) => {
      const pane = el.closest('.el-tab-pane')?.id
      el.setAttribute('aria-label', pane === 'pane-lecture' ? '讲义正文编辑器' : '笔记正文编辑器')
    })
  }
  // CodeMirror 在父组件 DOM 更新之后才初始化，补几次覆盖异步挂载
  apply()
  setTimeout(apply, 300)
  setTimeout(apply, 900)
}
watch([editorTab, detail], labelEditors, { flush: 'post' })
onMounted(labelEditors)

const noteCount = ref(0)
const busy = ref(false)
const loadSeq = ref(0)

const state = computed(() => detail.value?.revisions.at(-1)?.state ?? 'draft')
const savedNote = computed(() => detail.value?.notes.find((n) => n.id === noteId.value)?.content ?? '')
const noteDirty = computed(() => noteDraft.value !== savedNote.value)
const lectureDirty = computed(() => lectureDraft.value !== (detail.value?.content ?? ''))
const dirty = computed(() => noteDirty.value || lectureDirty.value)
const noteTabLabel = computed(() => `笔记${noteDirty.value ? ' *' : ''}`)
const lectureTabLabel = computed(() => `讲义正文${lectureDirty.value ? ' *' : ''}`)

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

async function load(opts: { keepNote?: boolean; keepLecture?: boolean } = {}) {
  const mine = ++loadSeq.value
  loadError.value = ''
  try {
    const data = await getItem(itemId.value)
    if (mine !== loadSeq.value) return
    if (detail.value && detail.value.id !== itemId.value) {
      editorTab.value = 'note'
      noteDraft.value = ''
      lectureDraft.value = ''
    }
    detail.value = data
    noteCount.value = data.notes.length
    // 深链可指定 note；否则编辑最新一条（后端已按 id 排序）
    const wanted = Number(route.query.note)
    const note = data.notes.find((n) => n.id === wanted) ?? data.notes.at(-1)
    noteId.value = note?.id ?? null
    if (!opts.keepNote) noteDraft.value = note?.content ?? ''
    if (!opts.keepLecture) lectureDraft.value = data.content
  } catch (err) {
    // 直达 URL / 条目被随批次删除时不再永远骨架屏
    if (mine !== loadSeq.value) return
    loadError.value = err instanceof Error ? err.message : '条目加载失败'
  }
}

watch([itemId, () => route.query.note], () => void load(), { immediate: true })
useLeaveGuard(() => dirty.value)

function selectNote(id: number | string) {
  const wanted = Number(id)
  const note = detail.value?.notes.find((n) => n.id === wanted)
  if (!note) return
  noteId.value = note.id
  noteDraft.value = note.content
}

async function saveNote() {
  if (!noteDraft.value.trim()) {
    ElMessage.warning('笔记内容为空，未保存')
    return
  }
  busy.value = true
  try {
    const anchor = detail.value?.anchor_ms ?? 0
    if (noteId.value === null) {
      const { id } = await addNote(itemId.value, noteDraft.value, anchor)
      noteId.value = id
    } else {
      await updateNote(noteId.value, noteDraft.value, anchor)
    }
    ElMessage.success('笔记已保存')
    await load({ keepLecture: true })
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    busy.value = false
  }
}

async function saveLecture() {
  if (!lectureDirty.value) {
    ElMessage.info('讲义正文没有变化')
    return
  }
  busy.value = true
  try {
    await revise(itemId.value, undefined, lectureDraft.value)
    ElMessage.success('讲义正文已保存并追加版本')
    await load({ keepNote: true })
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    busy.value = false
  }
}

/** 状态流转与正文修改一次提交，避免“状态变了但版本快照还是旧正文” */
async function move(next: RevisionState) {
  busy.value = true
  try {
    const content = lectureDirty.value ? lectureDraft.value : ''
    await revise(itemId.value, next, content)
    await load({ keepNote: true })
  } catch (err) {
    ElMessage.error(`状态机拒绝：${err instanceof Error ? err.message : err}`)
  } finally {
    busy.value = false
  }
}

function loadVersion(snapshot: string) {
  lectureDraft.value = snapshot
  editorTab.value = 'lecture'
  ElMessage.info('已载入历史版本，保存后会追加为新版本')
}

function insertAnchor() {
  if (!detail.value) return
  const anchor = `\n> 锚点 \`[${clock(detail.value.anchor_ms)}]\` ${detail.value.title}\n`
  if (editorTab.value === 'note') noteDraft.value += anchor
  else lectureDraft.value += anchor
}
</script>

<template>
  <div v-if="detail">
    <div class="crumb">
      <el-link @click="router.push('/')">视频库</el-link>
      <span>/</span>
      <el-link @click="router.push(`/videos/${detail.video_id}`)">知识工作台</el-link>
      <span>/</span><span>笔记与讲义</span>
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
          <b>笔记与讲义</b>
          <span v-if="dirty" class="dirty">未保存</span>
          <el-button size="small" class="anchor-btn" @click="insertAnchor">插入时间锚点</el-button>
        </template>
        <el-tabs v-model="editorTab">
          <el-tab-pane :label="noteTabLabel" name="note">
            <div v-if="noteCount > 1" class="note-pick">
              <span class="muted">该条目有 {{ noteCount }} 条笔记，可切换编辑：</span>
              <el-select :model-value="noteId" size="small" class="note-select" @change="selectNote">
                <el-option
                  v-for="n in detail.notes" :key="n.id"
                  :label="`#${n.id} · ${n.content.slice(0, 24) || '（空）'}`" :value="n.id"
                />
              </el-select>
            </div>
            <MdEditor v-model="noteDraft" :toolbars-exclude="['github', 'save', 'prettier']" />
            <el-button type="primary" :loading="busy" @click="saveNote">保存笔记</el-button>
            <p class="muted">笔记绑定条目时间点，支持从笔记跳回原片（用例「笔记与时间锚点」）。</p>
          </el-tab-pane>

          <el-tab-pane :label="lectureTabLabel" name="lecture">
            <el-alert
              type="info"
              :closable="false"
              show-icon
              class="multi"
              title="保存正文会追加一条版本记录；状态流转会同时提交当前正文。"
            />
            <MdEditor v-model="lectureDraft" :toolbars-exclude="['github', 'save', 'prettier']" />
            <el-button type="primary" :loading="busy" @click="saveLecture">保存正文并追加版本</el-button>
            <p class="muted">讲义正文是导出文稿与版本快照的来源；笔记是绑定时间点的附加批注。</p>
          </el-tab-pane>
        </el-tabs>
      </el-card>

      <el-card class="history" shadow="never">
        <template #header><b>讲义状态与版本记录</b></template>
        <div class="state">
          当前：<el-tag size="small" :type="REVISION_TYPE[state] ?? 'info'">{{ REVISION_LABEL[state] ?? state }}</el-tag>
          <div class="flows">
            <el-button
              v-for="f in FLOW" :key="f.state" size="small"
              :disabled="!allowed(f.state) || busy" @click="move(f.state)"
            >{{ f.label }}</el-button>
          </div>
        </div>
        <el-timeline class="tl">
          <el-timeline-item v-for="r in detail.revisions" :key="r.id" :timestamp="fmtDateTime(r.edited_at)" placement="top">
            <div>{{ REVISION_LABEL[r.state] ?? r.state }} · {{ EDITOR_LABEL[r.editor] ?? r.editor }}</div>
            <div class="snap">{{ r.snapshot.slice(0, 60) }}{{ r.snapshot.length > 60 ? '…' : '' }}</div>
            <el-link type="primary" class="load-version" @click="loadVersion(r.snapshot)">载入此版本</el-link>
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
@media (max-width: 1280px) {
  /* 三列最小宽度约 1048px；1280 不降两列会在 1081–1275px 区间横向溢出 */
  .notes { grid-template-columns: 320px minmax(0, 1fr); }
  .history { grid-column: 1 / -1; }
}
@media (max-width: 860px) {
  .notes { grid-template-columns: 1fr; }
  .history { grid-column: auto; }
}
.row { display: flex; align-items: center; gap: 8px; }
.ts { color: var(--el-color-primary, #3d6fd6); font-size: 12px; }
.title { margin: 8px 0; font-size: 15px; }
.content { line-height: 1.7; font-size: 13px; }
.quote { margin: 0; padding: 8px 10px; background: var(--vm-quote-bg, #f6f7f9); border-left: 3px solid var(--el-color-primary, #3d6fd6); font-size: 12px; }
.conflict { color: #b45309; font-size: 12px; }
.dirty { margin-left: 8px; color: #b45309; font-size: 12px; }
.anchor-btn { float: right; }
.multi { margin-bottom: 10px; }
.note-pick { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.note-select { width: 240px; max-width: 100%; }
.editor :deep(.md-editor-toolbar-wrapper) { height: auto; }
.editor :deep(.md-editor-toolbar) { flex-wrap: wrap; }
.state { font-size: 13px; margin-bottom: 12px; }
.flows { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.tl { margin-top: 14px; }
.snap { font-size: 12px; color: var(--vm-text-secondary, #4b5563); }
.load-version { font-size: 12px; margin-top: 4px; }
.muted { color: var(--vm-muted, #5f6b7d); font-size: 12px; }
</style>
