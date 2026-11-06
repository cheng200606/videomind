<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
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

const id = computed(() => Number(route.params.id))
const rerunning = ref(false)
onMounted(() => void store.open(id.value))
watch(id, (v) => { if (v) void store.open(v) })
// SSE 连接跟着进度页走：离开页面就断开，别挂在根组件上泄漏
onUnmounted(() => store.stopProgress())

const isRunning = computed(() => ['pending', 'running'].includes(store.current?.status ?? ''))
const isTerminal = computed(() => ['succeeded', 'partial', 'failed'].includes(store.current?.status ?? ''))

/** 表格插槽里的 row 是 any，经这里转成有类型的索引，避免以 any 下标撞 Record */
function statusOf(row: VideoState, stage: Stage): StageStatus {
  return row.stages[stage]
}

async function confirm(message: string, title: string): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, title, {
      type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消'
    })
    return true
  } catch {
    return false
  }
}

/** 整批重跑：后端已幂等（先清派生数据再逐条解析），单条失败不拖批；会清掉笔记/修订 */
async function reparseAll() {
  if (!await confirm('整批重跑会重建所有条目，并清除已有笔记与修订记录。确认继续？', '整批重跑')) return
  rerunning.value = true
  try {
    await reparseBatch(id.value)
    ElMessage.success('已开始整批重跑，进度见下方事件流')
    await store.open(id.value)
  } catch (err) {
    ElMessage.error(`重跑失败：${err instanceof Error ? err.message : err}`)
  } finally {
    rerunning.value = false
  }
}

/** 单条重试：只重置这一条的四个阶段，不动整批（用例 3）；同样会清掉该条笔记/修订 */
async function retry(row: VideoState) {
  if (!await confirm(`重试「${row.file_name ?? '该视频'}」会重建它的条目，并清除该条已有笔记与修订。确认继续？`, '单条重试')) return
  try {
    await retryVideo(row.id)
    ElMessage.success('已提交单条重试，进度见下方事件流')
    await store.open(id.value)
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
      <div class="head-actions">
        <span :title="isTerminal ? '' : '批次尚未解析完成'">
          <el-button size="small" :disabled="!isTerminal" @click="router.push(`/batches/${id}/export`)">导出批次文稿</el-button>
        </span>
        <el-button size="small" :loading="rerunning" :disabled="!isTerminal" @click="reparseAll">整批重跑</el-button>
        <el-button size="small" @click="router.push('/')">返回视频库</el-button>
      </div>
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
          <div class="file" :title="row.file_name || row.path">{{ row.file_name || row.path.split(/[\\/]/).pop() }}</div>
          <div v-if="row.error" class="err" :title="row.error">{{ row.error }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="96" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="STATUS_TYPE[row.status] ?? 'info'" disable-transitions>
            {{ STATUS_LABEL[row.status] ?? row.status }}
          </el-tag>
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
      <el-table-column label="操作" width="190" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" :disabled="isRunning || row.status === 'running'" @click="retry(row)">重试本条</el-button>
          <el-button size="small" type="primary" :disabled="row.status === 'pending' || row.status === 'running'" @click="router.push(`/videos/${row.id}`)">
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
  <el-alert
    v-else-if="store.error"
    type="error"
    :closable="false"
    show-icon
    :title="`批次加载失败：${store.error}`"
    class="alert"
  >
    <el-button size="small" @click="router.push('/')">返回视频库</el-button>
  </el-alert>
  <el-skeleton v-else :rows="6" animated />
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.head h2 { margin: 0; font-size: 18px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-left: auto; }
.alert { margin-bottom: 12px; }
.file { font-size: 13px; word-break: break-all; }
.err { margin-top: 4px; color: #b42318; font-size: 12px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.stream { margin-top: 16px; }
.evt { display: flex; align-items: center; gap: 10px; font-size: 12px; padding: 3px 0; flex-wrap: wrap; }
.muted { color: var(--vm-muted, #5f6b7d); }
@media (max-width: 800px) {
  .head-actions { margin-left: 0; }
}
</style>
