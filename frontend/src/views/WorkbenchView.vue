<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { bindTag, dismissTag, getItem, getItems, getTranscript, getVideo, listTags, mediaUrl } from '../api/client'
import { clock } from '../api/labels'
import type { Item, ItemDetail, Mark, TagInfo, VideoMeta } from '../api/types'
import ArtifactPanel from '../components/ArtifactPanel.vue'
import EvidenceDrawer from '../components/EvidenceDrawer.vue'
import EvidenceTimeline from '../components/EvidenceTimeline.vue'

const route = useRoute()
const router = useRouter()
const videoId = Number(route.params.id)

const video = ref<VideoMeta | null>(null)
const items = ref<Item[]>([])
const transcript = ref<{ start_ms: number; end_ms: number; text: string }[]>([])
const tags = ref<TagInfo[]>([])
const newTag = ref('')
const loadError = ref('')
const selected = ref<ItemDetail | null>(null)
const drawer = ref(false)
const player = ref<InstanceType<typeof EvidenceTimeline> | null>(null)

const chapters = computed(() => {
  const summary = items.value.find((i) => i.type === 'summary')
  return ((summary?.payload as { chapters?: { title: string; start_ms: number; gist: string }[] })?.chapters ?? [])
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
  tags.value = (await listTags('video', videoId)).filter((t) => t.bound)
}

function openQueryItem() {
  const wanted = Number(route.query.item)
  if (!wanted || !items.value.length) return
  const item = items.value.find((i) => i.id === wanted)
  if (item) select(item)
}

onMounted(async () => {
  try {
    // 三个接口本来互不依赖，并行拉比串行省一半白屏时间
    const [v, its, trs] = await Promise.all([
      getVideo(videoId), getItems(videoId), getTranscript(videoId)
    ])
    video.value = v
    items.value = its
    transcript.value = trs
    openQueryItem()
    // 标签失败不阻塞工作台主体
    await loadTags().catch(() => { tags.value = [] })
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err)
  }
})
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
async function adoptTag(t: TagInfo) {
  await bindTag(t.name, 'video', videoId)
  await loadTags()
}

async function dismissTagChip(t: TagInfo) {
  await dismissTag(t.id, 'video', videoId)
  await loadTags()
}

async function addTag() {
  const name = newTag.value.trim()
  if (!name) return
  await bindTag(name, 'video', videoId)
  newTag.value = ''
  await loadTags()
}
</script>

<template>
  <div v-if="video">
    <div class="crumb">
      <el-link @click="router.push('/')">视频库</el-link>
      <span>/</span>
      <el-link @click="router.push(`/batches/${video.batch_id}`)">批次进度</el-link>
      <span>/</span><span>知识工作台</span>
    </div>
    <el-alert
      v-if="video.error"
      type="error"
      :closable="false"
      show-icon
      class="alert"
      :title="`该视频解析失败：${video.error}`"
    />
    <div class="workbench">
      <div class="col left">
        <h3 class="t">章节大纲</h3>
        <ul class="outline">
          <li
            v-for="(c, i) in chapters" :key="i"
            role="button" tabindex="0"
            @click="seek(c.start_ms)"
            @keydown.enter="seek(c.start_ms)"
            @keydown.space.prevent="seek(c.start_ms)"
          >
            <span class="ts">{{ clock(c.start_ms) }}</span>
            <div>
              <div>{{ c.title }}</div>
              <div class="gist">{{ c.gist }}</div>
            </div>
          </li>
        </ul>

        <h3 class="t">原话转写（{{ transcript.length }} 句）</h3>
        <ul class="outline scroll">
          <li
            v-for="(s, i) in transcript" :key="i"
            role="button" tabindex="0"
            @click="seek(s.start_ms)"
            @keydown.enter="seek(s.start_ms)"
            @keydown.space.prevent="seek(s.start_ms)"
          >
            <span class="ts">{{ clock(s.start_ms) }}</span>
            <span class="txt">{{ s.text }}</span>
          </li>
        </ul>
      </div>

      <div class="col center">
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

      <div class="col right">
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
            <el-link v-if="t.suggested_by_ai" type="primary" class="op" @click="adoptTag(t)">采纳</el-link>
            <el-link type="danger" class="op" @click="dismissTagChip(t)">驳回</el-link>
          </el-tag>
          <el-input v-model="newTag" size="small" placeholder="加标签，回车绑定" class="tag-input" @keyup.enter="addTag" />
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
.crumb { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 12px; color: var(--vm-muted, #5f6b7d); flex-wrap: wrap; }
.alert { margin-bottom: 12px; }
/* 三列弹性收缩：1280 默认窗宽不溢出，窄窗按断点单列堆叠（产物列不可见是此前实测缺陷） */
.workbench { display: grid; grid-template-columns: minmax(220px, 300px) minmax(320px, 1fr) minmax(320px, 420px); gap: 14px; align-items: start; }
@media (max-width: 1080px) {
  .workbench { grid-template-columns: 1fr; }
  .col { min-height: auto; }
  /* 窄屏先给播放器与产物，大纲/转写放后面，避免一屏全是转写 */
  .col.center { order: 1; }
  .col.right { order: 2; }
  .col.left { order: 3; }
}
.col { background: #fff; border: 1px solid var(--vm-border, #e6e8eb); border-radius: 8px; padding: 12px; min-height: 70vh; }
.t { font-size: 13px; color: var(--vm-text-secondary, #4b5563); margin: 6px 0 8px; }
.outline { list-style: none; margin: 0 0 12px; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.outline li { display: flex; gap: 8px; padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.outline li:hover { background: #f2f5fb; }
.outline li:focus-visible { outline: 2px solid var(--el-color-primary, #3d6fd6); outline-offset: 1px; }
.outline.scroll { max-height: 40vh; overflow: auto; }
.ts { color: var(--el-color-primary, #3d6fd6); font-variant-numeric: tabular-nums; flex: none; width: 48px; }
.gist { color: var(--vm-muted, #5f6b7d); font-size: 12px; }
.tip { font-size: 12px; color: var(--vm-muted, #5f6b7d); margin-top: 10px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.tagbar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 10px 0 4px; }
.tchip { height: auto; padding: 3px 8px; }
.op { margin-left: 6px; font-size: 11px; vertical-align: baseline; }
.tag-input { width: 120px; }
.tag-hint { font-size: 12px; color: var(--vm-muted, #5f6b7d); }
</style>
