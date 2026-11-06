<script setup lang="ts">
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { Film, Search, Setting, Upload } from '@element-plus/icons-vue'
import { computed, markRaw, onBeforeUnmount, onMounted, ref, type Component } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

/**
 * 侧边栏三层导航模型的 L1：只有无数据参数的全局路由才配入侧栏；
 * 详情页（进度/工作台/笔记/导出）走面包屑定位，不做成菜单项（入口冗余防线）。
 * 分组与顺序依据：工作区按使用频率（库 > 上传 > 检索），低频配置沉到「系统」。
 */
const groups: { title: string; items: { name: string; label: string; icon: Component }[] }[] = [
  {
    title: '工作区',
    items: [
      { name: 'library', label: '视频库', icon: markRaw(Film) },
      { name: 'upload', label: '批量上传', icon: markRaw(Upload) },
      { name: 'search', label: '知识检索', icon: markRaw(Search) }
    ]
  },
  {
    title: '系统',
    items: [{ name: 'settings', label: '设置', icon: markRaw(Setting) }]
  }
]
const allItems = groups.flatMap((g) => g.items)

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

/** 子页面没有独立菜单项时回到所属入口（面包屑根「视频库」），避免侧栏全程无高亮 */
const activeMenu = computed(() => {
  const name = route.name as string | undefined
  if (name === 'settings' || name === 'upload' || name === 'search') return name
  return 'library'
})
</script>

<template>
  <el-config-provider :locale="zhCn">
    <el-container class="shell" :class="{ mobile }">
      <el-aside class="side">
        <div class="brand">
          <img class="logo" src="/favicon.svg" alt="" aria-hidden="true" />
          <div class="bt">
            <strong>VideoMind 视析</strong>
            <span>视频知识结构化平台</span>
          </div>
        </div>
        <!-- 桌面端：分组垂直菜单；移动端顶栏塞不下分组标题，退化为平铺 -->
        <el-menu v-if="!mobile" :router="true" :default-active="activeMenu" :ellipsis="false">
          <el-menu-item-group v-for="g in groups" :key="g.title" :title="g.title">
            <el-menu-item v-for="n in g.items" :key="n.name" :index="n.name" :route="{ name: n.name }">
              <el-icon :size="18"><component :is="n.icon" /></el-icon>
              <span>{{ n.label }}</span>
            </el-menu-item>
          </el-menu-item-group>
        </el-menu>
        <el-menu v-else mode="horizontal" :router="true" :default-active="activeMenu" :ellipsis="false">
          <el-menu-item v-for="n in allItems" :key="n.name" :index="n.name" :route="{ name: n.name }">
            {{ n.label }}
          </el-menu-item>
        </el-menu>
        <p class="hint">识别结果仅供参考</p>
      </el-aside>
      <el-main class="main">
        <RouterView v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </el-main>
    </el-container>
  </el-config-provider>
</template>

<style>
html, body, #app { height: 100%; margin: 0; }
.shell { height: 100%; }
.side {
  width: 200px; flex: none;
  background: var(--vm-sidebar-bg, linear-gradient(180deg, #1e2534 0%, #161c2a 100%));
  color: #dbe1ea;
}
.brand { padding: 18px 16px 14px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.08); margin-bottom: 6px; }
.logo { width: 28px; height: 28px; flex: none; }
.brand .bt { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.brand strong { font-size: 15px; line-height: 1.2; }
.brand span { font-size: 12px; color: #9aa6b8; }
.hint { padding: 12px 16px; font-size: 12px; color: #9aa6b8; }
.main { background: linear-gradient(180deg, #eef2f9 0%, var(--vm-bg, #f4f6fa) 280px, var(--vm-bg, #f4f6fa) 100%); min-width: 0; }
.el-menu { border-right: none; background: transparent; }
/* 菜单项胶囊化：内缩留出圆角空间，激活态用主色弱底 */
.side .el-menu { padding: 0 10px; }
.side .el-menu-item {
  color: #b7c0d0;
  border-radius: var(--vm-radius, 8px);
  margin: 2px 0;
  height: 40px;
  --el-menu-base-level-padding: 12px;
  transition: background-color 0.15s ease, color 0.15s ease;
}
/* 非激活菜单项提高对比度：深底上默认色读不清（实测截图确认） */
.side .el-menu-item:hover { background: rgba(255, 255, 255, 0.06); color: #e6ebf3; }
.side .el-menu-item.is-active { background: rgba(61, 111, 214, 0.22); }
.side .el-menu-item .el-icon { color: inherit; }
/* 分组标题与菜单项文字左缘对齐（菜单内缩 10px + 项内边距 12px） */
.side .el-menu-item-group__title { color: #7c8aa0; font-size: 11px; letter-spacing: 0.06em; padding: 14px 12px 4px; }

/* 页面切换过渡：进入上浮淡入、离开快速淡出（reduced-motion 时全局关闭） */
.page-enter-active { transition: opacity 0.18s ease-out, transform 0.18s ease-out; }
.page-leave-active { transition: opacity 0.12s ease-in; }
.page-enter-from { opacity: 0; transform: translateY(6px); }
.page-leave-to { opacity: 0; }

@media (max-width: 900px) {
  .side { width: 150px; }
  .brand { padding: 14px 10px 10px; }
  .brand strong { font-size: 14px; white-space: nowrap; }
  .brand .bt span { display: none; }
}

/* 移动端：侧栏变顶部横向导航，内容区全宽；不再保留 150px 固定侧栏 */
.shell.mobile { flex-direction: column; }
.shell.mobile .side {
  width: 100%; display: flex; align-items: center; gap: 8px;
  padding: 0 10px; min-height: 48px;
}
.shell.mobile .brand { padding: 8px 2px; flex: none; border-bottom: none; margin-bottom: 0; }
.shell.mobile .brand strong { font-size: 14px; white-space: nowrap; }
.shell.mobile .brand .bt span { display: none; }
.shell.mobile .el-menu { flex: 1; min-width: 0; border-right: none; border-bottom: none; padding: 0; }
.shell.mobile .side .el-menu-item { margin: 0; border-radius: 0; height: auto; min-height: 40px; }
.shell.mobile .el-menu--horizontal > .el-menu-item { height: 44px; line-height: 44px; padding: 0 10px; }
/* 顶栏 4 项在 ≤390px 放不下：允许横向滑动，滚动条隐藏保持观感 */
.shell.mobile .el-menu--horizontal { overflow-x: auto; scrollbar-width: none; }
.shell.mobile .el-menu--horizontal::-webkit-scrollbar { display: none; }
.shell.mobile .hint { display: none; }
.shell.mobile .main { padding: 12px; min-height: 0; }
</style>
