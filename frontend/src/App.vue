<script setup lang="ts">
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const nav = [
  { name: 'library', label: '视频库' },
  { name: 'upload', label: '批量上传' },
  { name: 'settings', label: '设置' }
]

const mobile = ref(false)
let media: MediaQueryList | null = null
function syncMobile(event: MediaQueryListEvent | MediaQueryList) {
  mobile.value = event.matches
}
onMounted(() => {
  media = window.matchMedia('(max-width: 900px)')
  syncMobile(media)
  media.addEventListener('change', syncMobile)
})
onBeforeUnmount(() => media?.removeEventListener('change', syncMobile))

/** 子页面没有独立菜单项时回到所属入口，避免侧栏全程无高亮 */
const activeMenu = computed(() => {
  const name = route.name as string | undefined
  if (name === 'settings') return 'settings'
  if (name === 'upload') return 'upload'
  return 'library'
})
</script>

<template>
  <el-config-provider :locale="zhCn">
    <el-container class="shell" :class="{ mobile }">
      <el-aside class="side">
        <div class="brand">
          <strong>VideoMind 视析</strong>
          <span>视频知识结构化平台</span>
        </div>
        <el-menu
          :router="true"
          :default-active="activeMenu"
          :mode="mobile ? 'horizontal' : 'vertical'"
          :ellipsis="false"
        >
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
  </el-config-provider>
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

/* 移动端：侧栏变顶部横向导航，内容区全宽；不再保留 150px 固定侧栏 */
.shell.mobile { flex-direction: column; }
.shell.mobile .side {
  width: 100%; display: flex; align-items: center; gap: 8px;
  padding: 0 10px; min-height: 48px;
}
.shell.mobile .brand { padding: 8px 2px; flex: none; }
.shell.mobile .brand strong { font-size: 14px; white-space: nowrap; }
.shell.mobile .brand span { display: none; }
.shell.mobile .el-menu { flex: 1; min-width: 0; border-right: none; border-bottom: none; }
.shell.mobile .el-menu--horizontal > .el-menu-item { height: 44px; line-height: 44px; padding: 0 10px; }
.shell.mobile .hint { display: none; }
.shell.mobile .main { padding: 12px; min-height: 0; }
</style>
