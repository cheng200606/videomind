<script setup lang="ts">
import type { Confidence } from '@/api/types'

defineProps<{ confidence: Confidence }>()

const TEXT: Record<Confidence, string> = {
  explicit: '明述',
  inferred: '推断',
  low: '低置信'
}
const TYPE: Record<Confidence, 'success' | 'warning' | 'danger'> = {
  explicit: 'success',
  inferred: 'warning',
  low: 'danger'
}
</script>

<template>
  <el-tag :type="TYPE[confidence]" size="small" effect="light" disable-transitions>
    {{ TEXT[confidence] }}
  </el-tag>
</template>
