<script setup lang="ts">
/**
 * 统一页头：语义化面包屑 + 页标题 + 状态 tag 插槽 + 动作插槽。
 * 面包屑承担数据层级回退（视频库 → 批次 → 视频 → 当前页），
 * 详情页不再各自手拼 crumb、也不再散落「返回视频库」按钮。
 */
defineProps<{
  title: string
  subtitle?: string
  /** 按层级给出；最后一项是当前页，不传 to */
  crumbs?: { label: string; to?: string }[]
}>()
</script>

<template>
  <header class="ph">
    <el-breadcrumb v-if="crumbs?.length" separator="/" class="crumb">
      <el-breadcrumb-item v-for="(c, i) in crumbs" :key="i" :to="c.to">
        {{ c.label }}
      </el-breadcrumb-item>
    </el-breadcrumb>
    <div class="row">
      <h2 class="vm-page-title">{{ title }}</h2>
      <slot name="tag" />
      <div class="acts">
        <slot name="actions" />
      </div>
    </div>
    <p v-if="subtitle" class="sub">{{ subtitle }}</p>
  </header>
</template>

<style scoped>
.ph { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.acts { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-left: auto; }
.sub { margin: 0; font-size: 12px; color: var(--vm-muted, #5f6b7d); }
.crumb :deep(.el-breadcrumb__item) { font-size: 12px; }
</style>
