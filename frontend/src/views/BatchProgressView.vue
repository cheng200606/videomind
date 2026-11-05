<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { reparseBatch, retryVideo } from '../api/client'
import {
  EVENT_STAGE_LABEL, STAGE_LABEL, STAGE_STATUS_LABEL, STAGE_STATUS_TYPE, STATUS_LABEL, STATUS_TYPE, fmtTime
} from '../api/labels'
import type { Stage, StageStatus, VideoState } from '../api/types'
import { useBatchStore } from '../stores/batch'

const route = useRoute()
const router = useRouter()
const store = useBatchStore()

const id = Number(route.params.id)
onMounted(() => void store.open(id))
watch(() => route.params.id, (v) => v && store.open(Number(v)))
// SSE 连接跟着进度页走：离开页面就断开，别挂在根组件上泄漏
onUnmounted(() => store.stopProgress())

/** 表格插槽里的 row 是 any，经这里转成有类型的索引，避免以 any 下标撞 Record */
function statusOf(row: VideoState, stage: Stage): StageStatus {
  return row.stages[stage]
}

const rerunning = ref(false)
/** 整批重跑：后端已幂等（先清派生数据再逐条解析），单条失败不拖批 */
async function reparseAll() {
  rerunning.value = true
  try {
    await reparseBatch(id)
    ElMessage.success('已开始整批重跑，进度见下方事件流')
    // 原批次大概率已终态、SSE 流已收：重新拉快照并订阅
    await store.open(id)
  } catch (err) {
    ElMessage.error(`重跑失败：${err instanceof Error ? err.message : err}`)
  } finally {
    rerunning.value = false
  }
}

/** 单条重试：只重置这一条的四个阶段，不动整批（用例 3） */
async function retry(videoId: number) {
  try {
    await retryVideo(videoId)
    ElMessage.success('已提交单条重试，进度见下方事件流')
  } catch (err) {
    ElMessage.error(`重试失败：${err instanceof Error ? err.message : err}`)
  }
}
</script>

<template>
  <div v-if="store.current">
    <div class="head">
      <h2>{{ store.current.name }}</h2>
      <el-tag :type="STATUS_TYPE[store.current.status] ?? 'info'">{{ STATUS_LABEL[store.current.status] ?? store.current.status }}</el-tag>
      <el-button size="small" @click="router.push(`/batches/${id}/export`)">导出批次文稿</el-button>
      <el-button size="small" :loading="rerunning" @click="reparseAll">整批重跑</el-button>
    </div>

    <el-alert
      v-if="store.current.status === 'partial'"
      type="warning"
      :closable="false"
      show-icon
      title="批次部分成功：失败条目可单条重试，已成功的结果不会重跑"
      class="alert"
    />

    <el-table :data="store.current.videos" border>
      <el-table-column label="视频" min-width="220">
        <template #default="{ row }">
          <span class="file">{{ row.path.split(/[\\/]/).pop() }}</span>
        </template>
      </el-table-column>
      <el-table-column
        v-for="(label, key) in STAGE_LABEL"
        :key="key"
        :label="label"
        width="120"
        align="center"
      >
        <template #default="{ row }">
          <el-tag size="small" :type="STAGE_STATUS_TYPE[statusOf(row, key as Stage)]" disable-transitions>
            {{ STAGE_STATUS_LABEL[statusOf(row, key as Stage)] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="190" align="center">
        <template #default="{ row }">
          <el-button size="small" :disabled="row.status === 'running'" @click="retry(row.id)">重试本条</el-button>
          <el-button size="small" type="primary" :disabled="row.status === 'pending'" @click="router.push(`/videos/${row.id}`)">
            工作台
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="stream" shadow="never">
      <template #header><b>解析事件流</b><span class="muted">（SSE 实时推送）</span></template>
      <div v-for="(e, i) in store.events.slice(-12)" :key="i" class="evt">
        <span class="muted">{{ fmtTime(e.ts) }}</span>
        <el-tag size="small" :type="STAGE_STATUS_TYPE[e.status as StageStatus] ?? 'info'">
          {{ EVENT_STAGE_LABEL[e.stage] ?? e.stage }} ·
          {{ STAGE_STATUS_LABEL[e.status] ?? STATUS_LABEL[e.status] ?? e.status }}
        </el-tag>
        <span>{{ e.message }}</span>
      </div>
      <el-empty v-if="!store.events.length" description="暂无事件" :image-size="60" />
    </el-card>
  </div>
  <el-skeleton v-else :rows="6" animated />
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.head h2 { margin: 0; font-size: 18px; }
.alert { margin-bottom: 12px; }
.file { font-size: 13px; word-break: break-all; }
.stream { margin-top: 16px; }
.evt { display: flex; align-items: center; gap: 10px; font-size: 12px; padding: 3px 0; }
.muted { color: #8b95a7; }
</style>
