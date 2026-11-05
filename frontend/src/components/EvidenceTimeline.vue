<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { Mark } from '../api/types'

const props = defineProps<{
  src: string
  marks: Mark[]
  durationMs: number
}>()

const emit = defineEmits<{ (e: 'time', ms: number): void }>()

const video = ref<HTMLVideoElement | null>(null)
const current = ref(0)

/** 不引播放器库：进度条上的证据刻度自绘，溯源跳转就是 video.currentTime 一次赋值 */
const total = computed(() => props.durationMs || (video.value?.duration ?? 0) * 1000 || 1)
const percent = computed(() => Math.min(100, (current.value / total.value) * 100))

function seek(ms: number) {
  if (!video.value) return
  video.value.currentTime = ms / 1000
  current.value = ms
  emit('time', ms)
}

function onTimeUpdate() {
  const ms = Math.round((video.value?.currentTime ?? 0) * 1000)
  current.value = ms
  emit('time', ms)
}

function onTrackClick(ev: MouseEvent) {
  const rect = (ev.currentTarget as HTMLElement).getBoundingClientRect()
  seek(((ev.clientX - rect.left) / rect.width) * total.value)
}

defineExpose({ seek })
onBeforeUnmount(() => video.value?.pause())
</script>

<template>
  <div class="player">
    <video ref="video" :src="src" controls class="screen" @timeupdate="onTimeUpdate" />

    <div class="track" @click="onTrackClick">
      <div class="played" :style="{ width: percent + '%' }" />
      <button
        v-for="(m, i) in marks"
        :key="i"
        class="tick"
        :class="m.kind ?? 'item'"
        :style="{ left: (m.ms / total) * 100 + '%' }"
        :title="m.label"
        @click.stop="seek(m.ms)"
      />
      <div class="head" :style="{ left: percent + '%' }" />
    </div>

    <div class="meta">
      <span class="now">{{ (current / 1000).toFixed(1) }}s</span>
      <span class="legend">刻度 = 结论在原片中的时间点，点击跳转</span>
    </div>
  </div>
</template>

<style scoped>
.player { background: #12151c; border-radius: 8px; padding: 12px; }
.screen { width: 100%; max-height: 62vh; display: block; border-radius: 6px; background: #000; }
.track { position: relative; height: 26px; margin-top: 10px; background: #2a3040; border-radius: 13px; cursor: pointer; }
.played { position: absolute; inset: 0 auto 0 0; background: #3d6fd6; border-radius: 13px; }
.head { position: absolute; top: 3px; width: 4px; height: 20px; margin-left: -2px; background: #fff; border-radius: 2px; }
.tick { position: absolute; top: 5px; width: 8px; height: 16px; padding: 0; border: none; border-radius: 3px; cursor: pointer; transform: translateX(-4px); }
.tick.chapter { background: #f0a202; }
.tick.item { background: #6ee7b7; }
.tick.evidence { background: #f87171; }
.meta { display: flex; justify-content: space-between; margin-top: 8px; color: #98a2b3; font-size: 12px; }
.now { font-variant-numeric: tabular-nums; color: #e5e7eb; }
</style>
