<script setup lang="ts">
import { ElMessage } from 'element-plus'
import type { UploadRawFile, UploadUserFile } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { createBatch, getEngines, getModelSettings } from '../api/client'
import type { EngineSettings, ModelSettings } from '../api/types'

const router = useRouter()
const name = ref('未命名批次')
const fileList = ref<UploadUserFile[]>([])
const busy = ref(false)
const uploadPercent = ref<number | null>(null)
const MAX_BYTES = 2 * 1024 ** 3

const engines = ref<EngineSettings | null>(null)
const modelMeta = ref<ModelSettings | null>(null)
const summaryError = ref('')

onMounted(async () => {
  try {
    const [e, m] = await Promise.all([getEngines(), getModelSettings()])
    engines.value = e
    modelMeta.value = m
  } catch (err) {
    summaryError.value = err instanceof Error ? err.message : '设置状态读取失败'
  }
})

async function submit() {
  const files = fileList.value.map((f) => f.raw).filter((f): f is UploadRawFile => !!f)
  if (!files.length) {
    ElMessage.warning('先选择至少一条本地视频')
    return
  }
  const tooLarge = files.find((f) => f.size > MAX_BYTES)
  if (tooLarge) {
    ElMessage.error(`${tooLarge.name} 超过 2GB，请先压缩或分段`)
    return
  }
  busy.value = true
  uploadPercent.value = 0
  try {
    const { id, rejected } = await createBatch(
      name.value.trim() || '未命名批次', files,
      (p) => { uploadPercent.value = p }
    )
    if (rejected.length) {
      ElMessage.warning(`已跳过 ${rejected.length} 个文件：${rejected.map((r) => `${r.filename}（${r.reason}）`).join('、')}`)
    }
    router.push(`/batches/${id}`)
  } catch (err) {
    ElMessage.error(`上传失败：${err instanceof Error ? err.message : err}`)
  } finally {
    busy.value = false
    uploadPercent.value = null
  }
}
</script>

<template>
  <el-card class="box">
    <template #header><b>批量导入本地视频</b></template>

    <el-form label-width="88px">
      <el-form-item label="批次名称">
        <el-input v-model="name" maxlength="40" show-word-limit placeholder="一次导入的 N 条视频归为一个批次" />
      </el-form-item>
      <el-form-item label="视频文件">
        <el-upload
          v-model:file-list="fileList"
          drag
          multiple
          :auto-upload="false"
          accept=".mp4,.mov,.mkv,.avi,.webm"
        >
          <div class="drop">把本地视频拖进来，或点击选择多个文件</div>
        </el-upload>
        <p class="hint">支持 mp4 / mov / mkv / avi / webm；单文件不超过 2GB；批内同名文件会被判重复并跳过（保留第一份）。</p>
      </el-form-item>
      <el-form-item label="当前配置">
        <div class="summary">
          <div v-if="summaryError" class="srow err">设置状态读取失败：{{ summaryError }}</div>
          <template v-else>
            <div class="srow">
              <span class="k">大模型</span>
              <el-tag v-if="modelMeta?.has_key" size="small" type="success">已配置</el-tag>
              <el-tag v-else size="small" type="warning">未配置 · 规则兜底</el-tag>
              <span class="v">{{ modelMeta ? `${modelMeta.provider} · ${modelMeta.model}` : '读取中…' }}</span>
              <el-button link type="primary" @click="router.push('/settings')">去设置</el-button>
            </div>
            <div class="srow">
              <span class="k">解析引擎</span>
              <span class="v">
                ASR {{ engines?.asr.current ?? '—' }} · OCR {{ engines?.ocr.current ?? '—' }} ·
                {{ engines?.output_schemas.length ?? 0 }} 类产物
              </span>
              <el-button link type="primary" @click="router.push('/settings')">修改</el-button>
            </div>
          </template>
        </div>
      </el-form-item>
    </el-form>

    <el-alert
      v-if="modelMeta && !modelMeta.has_key"
      type="warning"
      :closable="false"
      show-icon
      class="warn"
      title="未配置大模型 Key：解析仍可完成，但结构化阶段会使用规则兜底，质量有限。"
    />

    <p class="note">
      平台只处理你本机的文件：不留存、不下载、不分发任何第三方视频内容。
      识别结果仅供参考，请回看原片核对。
    </p>

    <el-progress v-if="busy && uploadPercent !== null" :percentage="uploadPercent" class="progress" />
    <el-button type="primary" :loading="busy" @click="submit">开始解析</el-button>
  </el-card>
</template>

<style scoped>
.box { max-width: 760px; margin: 0 auto; }
.hint { margin: 8px 0 0; font-size: 12px; color: var(--vm-muted, #5f6b7d); line-height: 1.6; }
.summary { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.srow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.srow.err { color: #b45309; }
.k { color: var(--vm-muted, #5f6b7d); flex: none; }
.v { color: var(--vm-text, #1f2937); }
.warn { margin-bottom: 12px; }
.progress { margin-bottom: 12px; max-width: 420px; }
.drop { padding: 26px; color: var(--vm-text-secondary, #4b5563); }
.note { font-size: 12px; color: var(--vm-muted, #5f6b7d); line-height: 1.7; margin: 0 0 14px; }
@media (max-width: 800px) {
  .box { max-width: none; }
}
</style>
