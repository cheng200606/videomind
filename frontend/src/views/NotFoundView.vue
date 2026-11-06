<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <el-result icon="warning" title="页面不存在" sub-title="链接可能已失效，或地址输入有误。">
    <template #extra>
      <el-button type="primary" @click="router.push('/')">返回视频库</el-button>
      <el-button @click="router.push('/upload')">去批量上传</el-button>
    </template>
  </el-result>
</template>
