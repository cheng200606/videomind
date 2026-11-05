<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { addNote, bindTag, dismissTag, getItems, getTranscript, getVideo, listTags, mediaUrl } from '../api/client'
import type { Item, Mark, TagInfo, VideoMeta } from '../api/types'
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
const selected = ref<Item | null>(null)
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

async function loadTags() {
  tags.value = (await listTags('video', videoId)).filter((t) => t.bound)
}

onMounted(async () => {
  try {
    // 三个接口本来互不依赖，并行拉比串行省一半白屏时间
    const [v, its, trs] = await Promise.all([
      getVideo(videoId), getItems(videoId), getTranscript(videoId), loadTags()
    ])
    video.value = v
    items.value = its
    transcript.value = trs
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err)
  }
})

function seek(ms: number) {
  player.value?.seek(ms)
}

function select(item: Item) {
  selected.value = item
  drawer.value = true
}

async function noteFromSelected() {
  if (!selected.value) return
  await addNote(selected.value.id, `关于「${selected.value.title}」：`, selected.value.anchor_ms)
  router.push(`/notes/${selected.value.id}`)
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
  <div v-if="video" class="workbench">
    <div class="col left">
      <h3 class="t">章节大纲</h3>
      <ul class="outline">
        <li v-for="(c, i) in chapters" :key="i" @click="seek(c.start_ms)">
          <span class="ts">{{ (c.start_ms / 1000).toFixed(0) }}s</span>
          <div>
            <div>{{ c.title }}</div>
            <div class="gist">{{ c.gist }}</div>
          </div>
        </li>
      </ul>

      <h3 class="t">原话转写（{{ transcript.length }} 句）</h3>
      <ul class="outline scroll">
        <li v-for="(s, i) in transcript" :key="i" @click="seek(s.start_ms)">
          <span class="ts">{{ (s.start_ms / 1000).toFixed(0) }}s</span>
          <span class="txt">{{ s.text }}</span>
        </li>
      </ul>
    </div>

    <div class="col center">
      <EvidenceTimeline
        ref="player"
        :src="mediaUrl(video.path)"
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
        <el-button size="small" :disabled="!selected" @click="noteFromSelected">从选中条目建笔记</el-button>
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
  <el-alert v-else-if="loadError" type="error" :closable="false" show-icon :title="`工作台加载失败：${loadError}`" />
  <el-skeleton v-else :rows="8" animated />
</template>

<style scoped>
.workbench { display: grid; grid-template-columns: 280px minmax(360px, 1fr) 420px; gap: 14px; align-items: start; }
.col { background: #fff; border: 1px solid #e6e8eb; border-radius: 8px; padding: 12px; min-height: 70vh; }
.t { font-size: 13px; color: #606a7b; margin: 6px 0 8px; }
.outline { list-style: none; margin: 0 0 12px; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.outline li { display: flex; gap: 8px; padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.outline li:hover { background: #f2f5fb; }
.outline.scroll { max-height: 40vh; overflow: auto; }
.ts { color: #3d6fd6; font-variant-numeric: tabular-nums; flex: none; width: 34px; }
.gist { color: #8b95a7; font-size: 12px; }
.tip { font-size: 12px; color: #8b95a7; margin-top: 10px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.tagbar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 10px 0 4px; }
.tchip { height: auto; padding: 3px 8px; }
.op { margin-left: 6px; font-size: 11px; vertical-align: baseline; }
.tag-input { width: 120px; }
.tag-hint { font-size: 12px; color: #8b95a7; }
</style>
