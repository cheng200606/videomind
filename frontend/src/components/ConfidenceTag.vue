<script setup lang="ts">
import { CONFIDENCE_LABEL, CONFIDENCE_TYPE } from '@/api/labels'
import type { Confidence } from '@/api/types'

defineProps<{ confidence: Confidence }>()
</script>

<template>
  <el-tag :type="CONFIDENCE_TYPE[confidence]" size="small" effect="light" disable-transitions>
    {{ CONFIDENCE_LABEL[confidence] }}
  </el-tag>
</template>
