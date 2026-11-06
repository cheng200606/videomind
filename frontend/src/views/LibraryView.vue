<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { defineAsyncComponent, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { deleteBatch } from '../api/client'
import { STATUS_LABEL, STATUS_TYPE, fmtDateTime } from '../api/labels'
import type { BatchSummary } from '../api/types'
import { useBatchStore } from '../stores/batch'

const SearchPanel = defineAsyncComponent(() => import('../components/LibrarySearchPanel.vue'))
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

const expanded = ref<string[]>([])

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
    <div class="head">
      <h2>视频库</h2>
      <el-button type="primary" @click="router.push('/upload')">新建批次</el-button>
    </div>

    <el-collapse v-model="expanded" class="search">
      <el-collapse-item name="on" title="跨视频检索 · 按标签 + 关键词定位条目（标签过滤，不是语义检索）">
        <Suspense>
          <SearchPanel v-if="expanded.includes('on')" />
          <template #fallback>
            <el-skeleton :rows="3" animated />
          </template>
        </Suspense>
      </el-collapse-item>
    </el-collapse>

    <el-skeleton v-if="loading" :rows="4" animated />
    <el-alert v-else-if="loadError" type="error" :closable="false" show-icon :title="`视频库加载失败：${loadError}`">
      <el-button size="small" @click="load">重试</el-button>
    </el-alert>
    <el-empty v-else-if="!store.batches.length" description="还没有批次，先去批量上传几条本地视频" />

    <div v-else class="grid">
      <el-card v-for="b in store.batches" :key="b.id" class="card" shadow="hover">
        <div class="name">{{ b.name }}</div>
        <div class="line">
          <el-tag size="small" :type="STATUS_TYPE[b.status] ?? 'info'">{{ STATUS_LABEL[b.status] ?? b.status }}</el-tag>
          <span>{{ b.video_count }} 条</span>
        </div>
        <div class="line muted">{{ fmtDateTime(b.created_at) }}</div>
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
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; gap: 10px; flex-wrap: wrap; }
.head h2 { margin: 0; }
.search { margin-bottom: 16px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); gap: 14px; }
.card .name { font-weight: 600; margin-bottom: 8px; }
.line { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; }
.muted { color: var(--vm-muted, #5f6b7d); }
.acts { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
</style>
