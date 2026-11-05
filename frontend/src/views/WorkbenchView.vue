<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { addNote, getItems, getTranscript, getVideo, mediaUrl } from '../api/client'
import type { Item, Mark, VideoMeta } from '../api/types'
import ArtifactPanel from '../components/ArtifactPanel.vue'
import EvidenceDrawer from '../components/EvidenceDrawer.vue'
import EvidenceTimeline from '../components/EvidenceTimeline.vue'

const route = useRoute()
const router = useRouter()
const videoId = Number(route.params.id)

const video = ref<VideoMeta | null>(null)
const items = ref<Item[]>([])
const transcript = ref<{ start_ms: number; end_ms: number; text: string }[]>([])
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

onMounted(async () => {
  video.value = await getVideo(videoId)
  items.value = await getItems(videoId)
  transcript.value = await getTranscript(videoId)
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
      <ArtifactPanel :items="items" @select="select" @seek="seek" />
    </div>

    <EvidenceDrawer v-model="drawer" :item="selected" @seek="seek" />
  </div>
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
</style>
