<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { clock, pct } from '../api/labels'
import type { Mark } from '../api/types'

const props = defineProps<{
  src: string
  marks: Mark[]
  durationMs: number
}>()

const emit = defineEmits<{ (e: 'time', ms: number): void }>()

const video = ref<HTMLVideoElement | null>(null)
const current = ref(0)
const mediaDuration = ref(0)
const videoError = ref('')

/** 不引播放器库：进度条上的证据刻度自绘，溯源跳转就是 video.currentTime 一次赋值 */
const total = computed(() => props.durationMs || mediaDuration.value || 1)
const percent = computed(() => pct(current.value, total.value))

function seek(ms: number) {
  if (!video.value) return
  const clamped = Math.min(total.value, Math.max(0, ms))
  video.value.currentTime = clamped / 1000
  current.value = clamped
  emit('time', clamped)
}

function onTimeUpdate() {
  const ms = Math.round((video.value?.currentTime ?? 0) * 1000)
  current.value = ms
  emit('time', ms)
}

function onLoadedMetadata() {
  mediaDuration.value = (video.value?.duration ?? 0) * 1000
}

function onVideoError() {
  videoError.value = '该文件无法在浏览器播放（或为测试占位文件）；转写与证据仍可走查。'
}

function onTrackClick(ev: MouseEvent) {
  const rect = (ev.currentTarget as HTMLElement).getBoundingClientRect()
  seek(((ev.clientX - rect.left) / rect.width) * total.value)
}

/** 轨道可键盘操作：方向键 ±5s，Home/End 到首尾；刻度按钮上的按键不冒泡触发 */
function onTrackKey(ev: KeyboardEvent) {
  if (ev.target !== ev.currentTarget) return
  if (ev.key === 'ArrowRight') seek(current.value + 5000)
  else if (ev.key === 'ArrowLeft') seek(current.value - 5000)
  else if (ev.key === 'Home') seek(0)
  else if (ev.key === 'End') seek(total.value)
  else return
  ev.preventDefault()
}

watch(() => props.src, () => {
  videoError.value = ''
  mediaDuration.value = 0
  current.value = 0
})

defineExpose({ seek })
onBeforeUnmount(() => video.value?.pause())
</script>

<template>
  <div class="player">
    <div class="screen-wrap">
      <video
        ref="video"
        :src="src"
        controls
        class="screen"
        @timeupdate="onTimeUpdate"
        @loadedmetadata="onLoadedMetadata"
        @error="onVideoError"
      />
      <div v-if="videoError" class="video-error">{{ videoError }}</div>
    </div>

    <div
      class="track"
      role="slider"
      tabindex="0"
      aria-label="播放进度与证据刻度"
      :aria-valuemin="0"
      :aria-valuemax="total"
      :aria-valuenow="current"
      :aria-valuetext="clock(current)"
      @click="onTrackClick"
      @keydown="onTrackKey"
    >
      <div class="played" :style="{ width: percent + '%' }" />
      <span
        v-for="(m, i) in marks"
        :key="i"
        class="tick"
        :class="m.kind ?? 'item'"
        :style="{ left: pct(m.ms, total) + '%' }"
        :title="m.label"
        aria-hidden="true"
        @click.stop="seek(m.ms)"
      />
      <div class="head" :style="{ left: percent + '%' }" />
    </div>

    <div class="meta">
      <span class="now">{{ clock(current) }}</span>
      <span class="legend">刻度 = 结论在原片中的时间点，点击跳转</span>
    </div>
  </div>
</template>

<style scoped>
.player { background: #12151c; border-radius: 8px; padding: 12px; }
.screen-wrap { position: relative; }
.screen { width: 100%; max-height: 62vh; display: block; border-radius: 6px; background: #000; }
.video-error {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  background: rgba(0, 0, 0, 0.72); color: #e5e7eb; padding: 20px; text-align: center;
  border-radius: 6px; font-size: 13px; line-height: 1.7;
}
.track { position: relative; height: 26px; margin-top: 10px; background: #2a3040; border-radius: 13px; cursor: pointer; }
.track:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
.played { position: absolute; inset: 0 auto 0 0; background: var(--el-color-primary, #3d6fd6); border-radius: 13px; }
.head { position: absolute; top: 3px; width: 4px; height: 20px; margin-left: -2px; background: #fff; border-radius: 2px; }
.tick { position: absolute; top: 5px; width: 8px; height: 16px; padding: 0; border: none; border-radius: 3px; cursor: pointer; transform: translateX(-4px); }
.tick.chapter { background: #f0a202; }
.tick.item { background: #6ee7b7; }
.tick.evidence { background: #f87171; }
.meta { display: flex; justify-content: space-between; margin-top: 8px; color: #b7c0d0; font-size: 12px; gap: 10px; flex-wrap: wrap; }
.now { font-variant-numeric: tabular-nums; color: #e5e7eb; }
</style>
