<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { useBatchStore } from '../stores/batch'

const store = useBatchStore()
const router = useRouter()
onMounted(() => void store.refreshList())
</script>

<template>
  <div>
    <div class="head">
      <h2>视频库</h2>
      <el-button type="primary" @click="router.push('/upload')">新建批次</el-button>
    </div>

    <el-empty v-if="!store.batches.length" description="还没有批次，先去批量上传几条本地视频" />

    <div class="grid">
      <el-card v-for="b in store.batches" :key="b.id" class="card" shadow="hover">
        <div class="name">{{ b.name }}</div>
        <div class="line">
          <el-tag size="small" :type="b.status === 'succeeded' ? 'success' : b.status === 'failed' ? 'danger' : 'info'">
            {{ b.status }}
          </el-tag>
          <span>{{ b.video_count }} 条</span>
        </div>
        <div class="line muted">{{ new Date(b.created_at).toLocaleString() }}</div>
        <div class="acts">
          <el-button size="small" @click="router.push(`/batches/${b.id}`)">解析进度</el-button>
          <el-button size="small" @click="router.push(`/batches/${b.id}/export`)">导出文稿</el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.head h2 { margin: 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.card .name { font-weight: 600; margin-bottom: 8px; }
.line { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; }
.muted { color: #8b95a7; }
.acts { display: flex; gap: 8px; margin-top: 10px; }
</style>
