<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const nav = [
  { name: 'library', label: '视频库' },
  { name: 'upload', label: '批量上传' },
  { name: 'settings', label: '设置' }
]

/** 子页面没有独立菜单项时回到所属入口，避免侧栏全程无高亮 */
const activeMenu = computed(() => {
  const name = route.name as string | undefined
  if (name === 'settings') return 'settings'
  if (name === 'upload') return 'upload'
  return 'library'
})
</script>

<template>
  <el-container class="shell">
    <el-aside class="side">
      <div class="brand">
        <strong>VideoMind 视析</strong>
        <span>视频知识结构化平台</span>
      </div>
      <el-menu :router="true" :default-active="activeMenu">
        <el-menu-item v-for="n in nav" :key="n.name" :index="n.name" :route="{ name: n.name }">
          {{ n.label }}
        </el-menu-item>
      </el-menu>
      <p class="hint">识别结果仅供参考</p>
    </el-aside>
    <el-main class="main">
      <RouterView />
    </el-main>
  </el-container>
</template>

<style>
html, body, #app { height: 100%; margin: 0; }
.shell { height: 100%; }
.side { width: 188px; background: var(--vm-sidebar, #1f2430); color: #dbe1ea; flex: none; }
.brand { padding: 18px 16px 10px; display: flex; flex-direction: column; gap: 4px; }
.brand span { font-size: 12px; color: #9aa6b8; }
.hint { padding: 12px 16px; font-size: 12px; color: #9aa6b8; }
.main { background: var(--vm-bg, #f5f6f8); min-width: 0; }
.el-menu { border-right: none; background: transparent; }
/* 非激活菜单项提高对比度：深底上默认色读不清（实测截图确认） */
.side .el-menu-item { color: #b7c0d0; }
.side .el-menu-item:hover { background: rgba(255, 255, 255, 0.06); color: #e6ebf3; }
@media (max-width: 900px) {
  .side { width: 150px; }
  .brand { padding: 14px 10px 4px; }
  .brand strong { font-size: 14px; white-space: nowrap; }
  .brand span { display: none; }
}
</style>
