<script setup lang="ts">
import { computed } from 'vue'

import type { Item } from '../api/types'
import ConfidenceTag from './ConfidenceTag.vue'

const props = defineProps<{ item: Item | null; modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'seek', ms: number): void
}>()

const CHANNEL: Record<string, string> = { asr: '语音通道（听到的）', ocr: '画面通道（看到的）', both: '语音 + 画面' }

/** yueying 的关键帧落在 media_root 下时才可经 /media 静态挂载访问 */
const frameUrl = computed(() => {
  const p = props.item?.evidence?.frame_path ?? ''
  const name = p.split(/[\\/]/).pop()
  return name && p.includes('media') ? `/media/${name}` : ''
})

function clock(ms: number) {
  const total = Math.floor(ms / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    title="证据链"
    size="420px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="item" class="body">
      <div class="row">
        <span class="k">类型</span><span>{{ item.type }}</span>
        <ConfidenceTag :confidence="item.confidence" />
      </div>
      <h4 class="title">{{ item.title }}</h4>
      <p class="content">{{ item.content }}</p>

      <template v-if="item.evidence">
        <el-divider content-position="left">溯源</el-divider>
        <div class="row"><span class="k">时间点</span>
          <el-link type="primary" @click="emit('seek', item.evidence.start_ms)">
            {{ clock(item.evidence.start_ms) }} → {{ clock(item.evidence.end_ms) }}
          </el-link>
        </div>
        <div class="row"><span class="k">通道</span><span>{{ CHANNEL[item.evidence.channel] }}</span></div>
        <blockquote class="quote">{{ item.evidence.quote }}</blockquote>
        <el-image v-if="frameUrl" :src="frameUrl" fit="contain" class="frame" :preview-src-list="[frameUrl]" />
        <el-image v-else-if="item.evidence.frame_path" :src="''" class="frame missing">
          <template #error><div class="missing-tip">片段帧未挂载到 /media</div></template>
        </el-image>
      </template>

      <p class="disclaimer">识别结果仅供参考，请回看原片核对。</p>
    </div>
    <el-empty v-else description="未选择条目" />
  </el-drawer>
</template>

<style scoped>
.body { display: flex; flex-direction: column; gap: 10px; }
.row { display: flex; align-items: center; gap: 10px; }
.k { color: #8b95a7; width: 56px; font-size: 13px; }
.title { margin: 0; font-size: 16px; }
.content { margin: 0; line-height: 1.7; }
.quote { margin: 0; padding: 10px 12px; background: #f6f7f9; border-left: 3px solid #3d6fd6; color: #444; }
.frame { width: 100%; border-radius: 6px; }
.missing-tip { font-size: 12px; color: #a5adba; }
.disclaimer { font-size: 12px; color: #a5adba; margin-top: 6px; }
</style>
