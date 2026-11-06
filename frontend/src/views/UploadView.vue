<script setup lang="ts">
import { ElMessage } from 'element-plus'
import type { UploadRawFile, UploadUserFile } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { createBatch, getEngines, getModelSettings } from '../api/client'
import { ASR_LABEL, MODEL_PROVIDER_LABEL, OCR_LABEL } from '../api/labels'
import type { EngineSettings, ModelSettings } from '../api/types'
import { useLeaveGuard } from '../composables/useLeaveGuard'
import PageHeader from '../components/PageHeader.vue'

const router = useRouter()
const name = ref('未命名批次')
const fileList = ref<UploadUserFile[]>([])
const busy = ref(false)
const uploadPercent = ref<number | null>(null)
const controller = ref<AbortController | null>(null)
const leavingForResult = ref(false)
let cancelled = false
const MAX_BYTES = 2 * 1024 ** 3
const MAX_FILES = 20   // 与后端单批上限一致

const engines = ref<EngineSettings | null>(null)
const modelMeta = ref<ModelSettings | null>(null)
const summaryError = ref('')
const resolvedAsr = computed(() => engines.value?.asr.resolved ?? engines.value?.asr.current ?? '')
const usingMock = computed(() => resolvedAsr.value === 'mock')

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
  if (files.length > MAX_FILES) {
    ElMessage.error(`单批最多 ${MAX_FILES} 个文件（当前选择了 ${files.length} 个），请分批上传`)
    return
  }
  const ac = new AbortController()
  controller.value = ac
  cancelled = false
  busy.value = true
  uploadPercent.value = 0
  try {
    const { id, rejected } = await createBatch(
      name.value.trim() || '未命名批次', files,
      (p) => { uploadPercent.value = p },
      ac.signal
    )
    if (cancelled) return
    if (rejected.length) {
      ElMessage.warning(`已跳过 ${rejected.length} 个文件：${rejected.map((r) => `${r.filename}（${r.reason}）`).join('、')}`)
    }
    // 批次已创建：此时离开是去结果页，不能被“未保存”保护拦下
    leavingForResult.value = true
    router.push(`/batches/${id}`)
  } catch (err) {
    if (cancelled) ElMessage.info('已取消上传；若批次已创建，可在视频库删除')
    else ElMessage.error(`上传失败：${err instanceof Error ? err.message : err}`)
  } finally {
    controller.value = null
    busy.value = false
    uploadPercent.value = null
    cancelled = false
  }
}

function cancelUpload() {
  if (!controller.value) return
  cancelled = true
  controller.value.abort()
}

useLeaveGuard(() => !leavingForResult.value && (fileList.value.length > 0 || busy.value))
</script>

<template>
  <div class="page">
    <PageHeader title="批量上传" subtitle="一次导入的 N 条本地视频归为一个批次，解析全程在本机完成" />
    <div class="box vm-card">
      <el-form label-width="88px" class="form">
        <h3 class="sec"><span class="no vm-num">1</span>选择视频</h3>
        <el-form-item label="批次名称">
          <el-input v-model="name" maxlength="80" show-word-limit placeholder="一次导入的 N 条视频归为一个批次" />
        </el-form-item>
        <el-form-item label="视频文件">
          <el-upload
            v-model:file-list="fileList"
            drag
            multiple
            :auto-upload="false"
            :disabled="busy"
            accept=".mp4,.mov,.mkv,.avi,.webm"
          >
            <div class="drop">把本地视频拖进来，或点击选择多个文件</div>
          </el-upload>
          <p class="hint">支持 mp4 / mov / mkv / avi / webm；单文件不超过 2GB；单批最多 20 个文件；批内同名文件会被判重复并跳过（保留第一份）。</p>
        </el-form-item>

        <h3 class="sec"><span class="no vm-num">2</span>解析参数</h3>
        <el-form-item label="当前配置">
          <div class="summary">
            <div v-if="summaryError" class="srow err">设置状态读取失败：{{ summaryError }}</div>
            <template v-else>
              <div class="srow">
                <span class="k">大模型</span>
                <el-tag v-if="modelMeta?.has_key" size="small" type="success">已配置</el-tag>
                <el-tag v-else size="small" type="warning">未配置 · 规则兜底</el-tag>
                <span class="v">{{ modelMeta ? `${MODEL_PROVIDER_LABEL[modelMeta.provider] ?? modelMeta.provider} · ${modelMeta.model}` : '读取中…' }}</span>
                <el-button link type="primary" @click="router.push('/settings')">去设置</el-button>
              </div>
              <div class="srow">
                <span class="k">解析引擎</span>
                <span class="v">
                  ASR {{ ASR_LABEL[resolvedAsr] ?? resolvedAsr }} ·
                  OCR {{ OCR_LABEL[engines?.ocr.current ?? ''] ?? engines?.ocr.current ?? '—' }} ·
                  {{ engines?.output_schemas.length ?? 0 }} 类产物
                </span>
                <el-button link type="primary" @click="router.push('/settings')">修改</el-button>
              </div>
            </template>
          </div>
        </el-form-item>
      </el-form>

      <h3 class="sec"><span class="no vm-num">3</span>开始解析</h3>
      <el-alert
        v-if="modelMeta && !modelMeta.has_key"
        type="warning"
        :closable="false"
        show-icon
        class="warn"
        title="未配置大模型 Key：解析仍可完成，但结构化阶段会使用规则兜底，质量有限。"
      />
      <el-alert
        v-if="usingMock"
        type="warning"
        :closable="false"
        show-icon
        class="warn"
        title="当前 ASR 是演示样例：不会读取视频内容，生成的笔记会与视频无关。"
      >
        请先到设置页切换为「自动」或「Whisper 本地转写」。
      </el-alert>

      <p class="note">
        平台只处理你本机的文件：不留存、不下载、不分发任何第三方视频内容。
        识别结果仅供参考，请回看原片核对。
      </p>

      <el-progress v-if="busy && uploadPercent !== null" :percentage="uploadPercent" class="progress" />
      <el-button type="primary" :loading="busy" @click="submit">开始解析</el-button>
      <el-button v-if="busy" @click="cancelUpload">取消上传</el-button>
    </div>
  </div>
</template>

<style scoped>
.box { max-width: 760px; margin: 0 auto; padding: 18px 20px; }
.form { max-width: 100%; }
.sec { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: var(--vm-text, #1f2937); margin: 18px 0 12px; }
.form .sec:first-child { margin-top: 0; }
.no { width: 20px; height: 20px; border-radius: 50%; background: var(--el-color-primary, #3d6fd6); color: #fff; font-size: 12px; display: inline-flex; align-items: center; justify-content: center; flex: none; }
.hint { margin: 8px 0 0; font-size: 12px; color: var(--vm-muted, #5f6b7d); line-height: 1.6; }
.summary { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.srow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.srow.err { color: var(--vm-warning-text, #b45309); }
.k { color: var(--vm-muted, #5f6b7d); flex: none; }
.v { color: var(--vm-text, #1f2937); }
.warn { margin-bottom: 12px; }
.progress { margin-bottom: 12px; max-width: 420px; }
.drop { padding: 26px; color: var(--vm-text-secondary, #4b5563); }
.note { font-size: 12px; color: var(--vm-muted, #5f6b7d); line-height: 1.7; margin: 0 0 14px; }
@media (max-width: 900px) {
  .box { max-width: none; }
}
</style>
