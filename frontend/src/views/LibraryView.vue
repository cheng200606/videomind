<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { deleteBatch } from '../api/client'
import { STATUS_LABEL, STATUS_TYPE, fmtDateTime } from '../api/labels'
import type { BatchSummary } from '../api/types'
import PageHeader from '../components/PageHeader.vue'
import { useBatchStore } from '../stores/batch'

const store = useBatchStore()
const router = useRouter()
const loading = ref(true)
const loadError = ref('')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    await store.refreshList()
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)

/** 状态筛选：纯前端过滤，带计数；只列实际出现过的状态，避免一排灰色死选项 */
const statusFilter = ref('all')
const statusOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const b of store.batches) counts.set(b.status, (counts.get(b.status) ?? 0) + 1)
  const opts = [{ value: 'all', label: `全部 ${store.batches.length}` }]
  for (const s of ['running', 'pending', 'succeeded', 'partial', 'failed']) {
    if (counts.has(s)) opts.push({ value: s, label: `${STATUS_LABEL[s] ?? s} ${counts.get(s)}` })
  }
  return opts
})
const filtered = computed(() =>
  statusFilter.value === 'all' ? store.batches : store.batches.filter((b) => b.status === statusFilter.value)
)

/** 删除只清运行时数据（后端级联），解析中的批次按钮已禁用 */
async function removeBatch(b: BatchSummary) {
  try {
    await ElMessageBox.confirm(`删除批次「${b.name}」？解析产物与上传文件将一并清除。`, '删除批次', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await deleteBatch(b.id)
    ElMessage.success('批次已删除')
    await store.refreshList()
  } catch (err) {
    ElMessage.error(`删除失败：${err instanceof Error ? err.message : err}`)
  }
}

/** 空 PENDING 批次后端允许删除；运行中的批次禁止，其他状态均终态可删 */
function canDelete(b: BatchSummary): boolean {
  return b.status !== 'running' && !(b.status === 'pending' && b.video_count > 0)
}
</script>

<template>
  <div>
    <PageHeader title="视频库" :subtitle="`共 ${store.batches.length} 个批次`">
      <template #actions>
        <el-button type="primary" @click="router.push('/upload')">批量上传</el-button>
      </template>
    </PageHeader>

    <el-skeleton v-if="loading" :rows="4" animated />
    <el-alert v-else-if="loadError" type="error" :closable="false" show-icon :title="`视频库加载失败：${loadError}`">
      <el-button size="small" @click="load">重试</el-button>
    </el-alert>
    <el-empty v-else-if="!store.batches.length" description="还没有批次，先去批量上传几条本地视频" :image-size="60">
      <el-button type="primary" @click="router.push('/upload')">去批量上传</el-button>
    </el-empty>

    <template v-else>
      <el-radio-group v-model="statusFilter" class="filter" size="small" aria-label="按批次状态筛选">
        <el-radio-button v-for="o in statusOptions" :key="o.value" :value="o.value">{{ o.label }}</el-radio-button>
      </el-radio-group>

      <div v-if="filtered.length" class="grid">
        <el-card v-for="b in filtered" :key="b.id" class="card" shadow="never">
          <div class="name">{{ b.name }}</div>
          <div class="line">
            <el-tag size="small" :type="STATUS_TYPE[b.status] ?? 'info'">{{ STATUS_LABEL[b.status] ?? b.status }}</el-tag>
            <span class="vm-num">{{ b.video_count }} 条</span>
          </div>
          <div class="line muted vm-num">{{ fmtDateTime(b.created_at) }}</div>
          <div class="acts">
            <el-button size="small" @click="router.push(`/batches/${b.id}`)">解析进度</el-button>
            <el-button
              size="small"
              :disabled="!['succeeded', 'partial', 'failed'].includes(b.status)"
              @click="router.push(`/batches/${b.id}/export`)"
            >导出文稿</el-button>
            <el-button size="small" type="danger" plain :disabled="!canDelete(b)" @click="removeBatch(b)">
              删除
            </el-button>
          </div>
        </el-card>
      </div>
      <el-empty v-else description="该状态下暂无批次" :image-size="60" />
    </template>
  </div>
</template>

<style scoped>
.filter { margin-bottom: 14px; flex-wrap: wrap; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); gap: 14px; }
.card { border-radius: var(--vm-radius, 8px); transition: transform 0.18s ease, box-shadow 0.18s ease; }
.card:hover { transform: translateY(-2px); box-shadow: var(--vm-shadow-hover); }
@media (prefers-reduced-motion: reduce) {
  .card, .card:hover { transition: none; transform: none; }
}
.card .name { font-weight: 600; margin-bottom: 8px; word-break: break-all; }
.line { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; }
.muted { color: var(--vm-muted, #5f6b7d); }
.acts { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
</style>
