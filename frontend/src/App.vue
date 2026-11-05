<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()

const nav = [
  { name: 'library', label: '视频库' },
  { name: 'upload', label: '批量上传' }
]
</script>

<template>
  <el-container class="shell">
    <el-aside width="188px" class="side">
      <div class="brand">
        <strong>VideoMind 视析</strong>
        <span>视频知识结构化平台</span>
      </div>
      <el-menu :router="true" :default-active="(route.name as string)">
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
.side { background: #1f2430; color: #dbe1ea; }
.brand { padding: 18px 16px 10px; display: flex; flex-direction: column; gap: 4px; }
.brand span { font-size: 12px; color: #8b95a7; }
.hint { padding: 12px 16px; font-size: 12px; color: #6f7a8c; }
.main { background: #f5f6f8; }
.el-menu { border-right: none; background: transparent; }
/* 非激活菜单项提高对比度：深底上默认色读不清（实测截图确认） */
.side .el-menu-item { color: #b7c0d0; }
.side .el-menu-item:hover { background: rgba(255, 255, 255, 0.06); color: #e6ebf3; }
</style>
