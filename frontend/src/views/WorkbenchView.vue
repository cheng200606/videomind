<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { bindTag, dismissTag, getBatch, getItem, getItems, getTranscript, getVideo, listTags, mediaUrl } from '../api/client'
import { clock } from '../api/labels'
import type { Item, ItemDetail, Mark, TagInfo, VideoMeta, VideoState } from '../api/types'
import ArtifactPanel from '../components/ArtifactPanel.vue'
import EvidenceDrawer from '../components/EvidenceDrawer.vue'
import EvidenceTimeline from '../components/EvidenceTimeline.vue'
import PageHeader from '../components/PageHeader.vue'

const route = useRoute()
const router = useRouter()
const videoId = computed(() => Number(route.params.id))

const video = ref<VideoMeta | null>(null)
const items = ref<Item[]>([])
const transcript = ref<{ start_ms: number; end_ms: number; text: string }[]>([])
const tags = ref<TagInfo[]>([])
const newTag = ref('')
const loadError = ref('')
const selected = ref<ItemDetail | null>(null)
const drawer = ref(false)
const player = ref<InstanceType<typeof EvidenceTimeline> | null>(null)
/** 同批次的其他视频：给工作台一个不回退进度页的横向切换入口 */
const batchVideos = ref<VideoState[]>([])
const TRANSCRIPT_LIMIT = 5000   // 与后端 transcript 端点的上限一致

const chapters = computed(() => {
  const summary = items.value.find((i) => i.type === 'summary')
  return ((summary?.payload as { chapters?: { title: string; start_ms: number; gist: string }[] })?.chapters ?? [])
})

/** 摘要产物携带的诚实提示（如「转写超长，仅前 12000 字符参与结构化」），解析时落库 */
const summaryNotice = computed(() => {
  const summary = items.value.find((i) => i.type === 'summary')
  return ((summary?.payload as { notice?: string } | undefined)?.notice ?? '')
})

/** 左大纲 + 进度条刻度同源：点大纲条目 = 跳时间点，和右侧产物面板点击是同一个动作 */
const marks = computed<Mark[]>(() => [
  ...chapters.value.map((c) => ({ ms: c.start_ms, label: c.title, kind: 'chapter' as const })),
  ...items.value.filter((i) => i.type === 'key_points').map((i) => ({ ms: i.anchor_ms, label: i.title, kind: 'item' as const }))
])

const noteLabel = computed(() => {
  if (!selected.value) return '打开 / 新建笔记'
  return selected.value.notes.length ? '打开笔记' : '新建笔记'
})

async function loadTags() {
  tags.value = (await listTags('video', videoId.value)).filter((t) => t.bound)
}

function openQueryItem() {
  const wanted = Number(route.query.item)
  if (!wanted || !items.value.length) return
  const item = items.value.find((i) => i.id === wanted)
  if (item) select(item)
}

const loadSeq = ref(0)

async function load() {
  const mine = ++loadSeq.value
  if (!Number.isFinite(videoId.value)) {
    // 坏深链（/videos/abc）：不发起请求，直接给中文提示
    loadError.value = '链接无效：视频 ID 必须是数字'
    return
  }
  loadError.value = ''
  video.value = null
  items.value = []
  transcript.value = []
  tags.value = []
  batchVideos.value = []
  selected.value = null
  drawer.value = false
  try {
    // 三个接口本来互不依赖，并行拉比串行省一半白屏时间
    const [v, its, trs] = await Promise.all([
      getVideo(videoId.value), getItems(videoId.value), getTranscript(videoId.value)
    ])
    if (mine !== loadSeq.value) return
    video.value = v
    items.value = its
    transcript.value = trs
    openQueryItem()
    // 同批次列表失败不阻塞工作台主体
    void getBatch(v.batch_id).then((b) => { if (mine === loadSeq.value) batchVideos.value = b.videos }).catch(() => {})
    // 标签失败不阻塞工作台主体
    await loadTags().catch(() => { tags.value = [] })
  } catch (err) {
    if (mine !== loadSeq.value) return
    loadError.value = err instanceof Error ? err.message : String(err)
  }
}

watch(() => route.params.id, () => void load(), { immediate: true })
watch(() => route.query.item, openQueryItem)

function seek(ms: number) {
  player.value?.seek(ms)
}

function select(item: Item) {
  // 空详情占位让抽屉立即打开，冲突（F2）/修订/笔记随后由详情接口补齐
  selected.value = { ...item, conflicts: [], revisions: [], notes: [] }
  drawer.value = true
  void getItem(item.id)
    .then((detail) => {
      if (selected.value?.id === item.id) selected.value = detail
    })
    .catch(() => { /* 冲突信息拉不到不影响证据展示 */ })
}

function noteFromSelected() {
  if (!selected.value) return
  const latest = selected.value.notes.at(-1)
  router.push({
    path: `/notes/${selected.value.id}`,
    query: latest ? { note: String(latest.id) } : {}
  })
}

/** B5 两层标签的人工侧：AI 建议可采纳/驳回，也可手动绑定新标签（video 级） */
const tagBusy = ref(false)

async function runTag(action: () => Promise<void>, success: string) {
  if (tagBusy.value) return
  tagBusy.value = true
  try {
    await action()
    await loadTags()
    ElMessage.success(success)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '标签操作失败')
  } finally {
    tagBusy.value = false
  }
}

async function adoptTag(t: TagInfo) {
  await runTag(() => bindTag(t.name, 'video', videoId.value), '已采纳 AI 标签建议')
}

async function dismissTagChip(t: TagInfo) {
  const message = t.suggested_by_ai ? '已驳回 AI 标签建议' : '已移除标签'
  await runTag(() => dismissTag(t.id, 'video', videoId.value), message)
}

async function addTag() {
  const name = newTag.value.trim()
  if (!name) return
  await runTag(async () => {
    await bindTag(name, 'video', videoId.value)
    newTag.value = ''
  }, '标签已绑定')
}
</script>

<template>
  <div v-if="video">
    <PageHeader
      :title="video.file_name || video.path.split(/[\\/]/).pop() || '知识工作台'"
      :crumbs="[{ label: '视频库', to: '/' }, { label: '批次进度', to: `/batches/${video.batch_id}` }]"
    >
      <template #actions>
        <el-select
          v-if="batchVideos.length > 1"
          class="sib"
          size="small"
          :model-value="''"
          placeholder="切换同批次视频"
          aria-label="切换同批次视频"
          @change="(id: number | string) => router.push(`/videos/${Number(id)}`)"
        >
          <el-option
            v-for="v in batchVideos" :key="v.id" :value="v.id"
            :label="`${v.id === videoId ? '当前 · ' : ''}${v.file_name || v.path.split(/[\\/]/).pop()}`"
          />
        </el-select>
      </template>
    </PageHeader>
    <el-alert
      v-if="video.error"
      type="error"
      :closable="false"
      show-icon
      class="alert"
      :title="`该视频解析失败：${video.error}`"
    />
    <el-alert
      v-if="summaryNotice"
      type="warning"
      :closable="false"
      show-icon
      class="alert"
      :title="summaryNotice"
    />
    <div class="workbench">
      <div class="col vm-card left">
        <h3 class="t">章节大纲</h3>
        <el-empty
          v-if="!chapters.length"
          description="暂无章节大纲：可能仍在解析，或该视频没有结构化结果"
          :image-size="48"
        />
        <div v-else class="outline">
          <div
            v-for="(c, i) in chapters" :key="i"
            class="outline-item"
            role="button" tabindex="0"
            @click="seek(c.start_ms)"
            @keydown.enter="seek(c.start_ms)"
            @keydown.space.prevent="seek(c.start_ms)"
          >
            <span class="vm-ts">{{ clock(c.start_ms) }}</span>
            <div>
              <div>{{ c.title }}</div>
              <div class="gist">{{ c.gist }}</div>
            </div>
          </div>
        </div>

        <h3 class="t">原话转写（{{ transcript.length }} 句）</h3>
        <p v-if="transcript.length >= TRANSCRIPT_LIMIT" class="tip">
          转写过长，仅显示前 {{ TRANSCRIPT_LIMIT }} 段
        </p>
        <el-empty v-if="!transcript.length" description="暂无转写：可能仍在解析" :image-size="48" />
        <div v-else class="outline scroll">
          <div
            v-for="(s, i) in transcript" :key="i"
            class="outline-item"
            role="button" tabindex="0"
            @click="seek(s.start_ms)"
            @keydown.enter="seek(s.start_ms)"
            @keydown.space.prevent="seek(s.start_ms)"
          >
            <span class="vm-ts">{{ clock(s.start_ms) }}</span>
            <span class="txt">{{ s.text }}</span>
          </div>
        </div>
      </div>

      <div class="col vm-card center">
        <EvidenceTimeline
          ref="player"
          :src="video.media_url || mediaUrl(video.path)"
          :marks="marks"
          :duration-ms="video.duration_ms"
        />
        <p class="tip">
          播放器与刻度条为原生实现；点刻度 / 点大纲 / 点产物面板任意一处，都跳到同一时间点。
        </p>
      </div>

      <div class="col vm-card right">
        <div class="panel-head">
          <h3 class="t">结构化产物</h3>
          <el-button size="small" :disabled="!selected" @click="noteFromSelected">{{ noteLabel }}</el-button>
        </div>
        <div class="tagbar">
          <span v-if="!tags.length" class="tag-hint">暂无标签：AI 解析后会给视频级建议，也可手动绑定</span>
          <el-tag
            v-for="t in tags"
            :key="t.id"
            size="small"
            :type="t.suggested_by_ai ? 'warning' : 'info'"
            class="tchip"
          >
            {{ t.name }}<template v-if="t.suggested_by_ai"> · AI 建议</template>
            <el-link v-if="t.suggested_by_ai" type="primary" class="op" :disabled="tagBusy" @click="adoptTag(t)">采纳</el-link>
            <el-link type="danger" class="op" :disabled="tagBusy" @click="dismissTagChip(t)">
              {{ t.suggested_by_ai ? '驳回' : '移除' }}
            </el-link>
          </el-tag>
          <el-input
            v-model="newTag" size="small" placeholder="加标签，回车绑定"
            class="tag-input" :disabled="tagBusy" @keyup.enter="addTag"
          />
        </div>
        <ArtifactPanel :items="items" @select="select" @seek="seek" />
      </div>

      <EvidenceDrawer v-model="drawer" :item="selected" @seek="seek" />
    </div>
  </div>
  <el-alert v-else-if="loadError" type="error" :closable="false" show-icon :title="`工作台加载失败：${loadError}`">
    <el-button size="small" @click="router.push('/')">返回视频库</el-button>
  </el-alert>
  <el-skeleton v-else :rows="8" animated />
</template>

<style scoped>
.alert { margin-bottom: 12px; }
/* 三列弹性收缩：默认窗宽不溢出，≤900 单列堆叠（产物列不可见是此前实测缺陷） */
.workbench { display: grid; grid-template-columns: minmax(220px, 300px) minmax(320px, 1fr) minmax(320px, 420px); gap: 14px; align-items: start; }
@media (max-width: 900px) {
  .workbench { grid-template-columns: 1fr; }
  /* 窄屏先给播放器与产物，大纲/转写放后面，避免一屏全是转写 */
  .col.center { order: 1; }
  .col.right { order: 2; }
  .col.left { order: 3; }
}
.col { padding: 12px; min-width: 0; }
.t { font-size: 14px; color: var(--vm-text-secondary, #4b5563); margin: 6px 0 8px; }
.outline { margin: 0 0 12px; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.outline-item { display: flex; gap: 8px; padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.outline-item:hover { background: var(--vm-hover-tint, #f2f5fb); }
.outline-item:focus-visible { outline: 2px solid var(--el-color-primary, #3d6fd6); outline-offset: 1px; }
.outline.scroll { max-height: 40vh; overflow: auto; }
/* 时间码芯片定宽居中，保证多行列表的内容起始边对齐 */
.outline-item .vm-ts { width: 56px; }
.gist { color: var(--vm-muted, #5f6b7d); font-size: 12px; }
.tip { font-size: 12px; color: var(--vm-muted, #5f6b7d); margin-top: 10px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.tagbar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 10px 0 4px; }
.tchip { height: auto; padding: 3px 8px; }
.op { margin-left: 6px; font-size: 11px; vertical-align: baseline; }
.tag-input { width: 120px; }
.tag-hint { font-size: 12px; color: var(--vm-muted, #5f6b7d); }
.sib { width: 190px; }
</style>
