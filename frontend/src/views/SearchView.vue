<script setup lang="ts">
import { defineAsyncComponent } from 'vue'

import PageHeader from '../components/PageHeader.vue'

/** 检索面板保持异步加载：首屏不回退（v0.8.1 基线 474KB） */
const SearchPanel = defineAsyncComponent(() => import('../components/LibrarySearchPanel.vue'))
</script>

<template>
  <div>
    <PageHeader
      title="知识检索"
      subtitle="按标签 + 关键词跨视频定位条目（标签过滤，不是语义检索）；点击结果行跳转对应工作台"
    />
    <div class="vm-card panel">
      <Suspense>
        <SearchPanel />
        <template #fallback>
          <el-skeleton :rows="4" animated />
        </template>
      </Suspense>
    </div>
  </div>
</template>

<style scoped>
.panel { padding: 14px 16px; }
</style>
