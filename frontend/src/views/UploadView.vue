<script setup lang="ts">
import { ElMessage } from 'element-plus'
import type { UploadRawFile, UploadUserFile } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { createBatch, getEngines, setEngines } from '../api/client'
import type { EngineSettings } from '../api/types'

const router = useRouter()
const name = ref('未命名批次')
const fileList = ref<UploadUserFile[]>([])
const busy = ref(false)

/** 解析参数：对应 OcrEngine / AsrEngine / OutputSchemaStrategy 三个策略的运行时选择（页 11 的能力前置到批次） */
const engines = ref<EngineSettings | null>(null)
const asr = ref('mock')
const ocr = ref('none')
const schemas = ref<string[]>([])
const ALL_SCHEMAS = ['summary', 'key_points', 'uml_draft', 'code_blocks']

onMounted(async () => {
  engines.value = await getEngines()
  asr.value = engines.value.asr.current
  ocr.value = engines.value.ocr.current
  schemas.value = [...engines.value.output_schemas]
})

async function submit() {
  // el-upload 的 raw 是带 uid 的 UploadRawFile（File 的子类型），类型收窄后正好传给 createBatch
  const files = fileList.value.map((f) => f.raw).filter((f): f is UploadRawFile => !!f)
  if (!files.length) {
    ElMessage.warning('先选择至少一条本地视频')
    return
  }
  busy.value = true
  try {
    await setEngines({ asr: asr.value, ocr: ocr.value, output_schemas: schemas.value })
    const { id, rejected } = await createBatch(name.value.trim() || '未命名批次', files)
    if (rejected.length) {
      ElMessage.warning(`已跳过 ${rejected.length} 个文件：${rejected.map((r) => `${r.filename}（${r.reason}）`).join('、')}`)
    }
    router.push(`/batches/${id}`)
  } catch (err) {
    ElMessage.error(`上传失败：${err instanceof Error ? err.message : err}`)
  } finally {
    busy.value = false
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
      </el-form-item>
      <el-form-item label="解析参数">
        <div class="params">
          <el-select v-model="asr" class="p">
            <el-option v-for="o in engines?.asr.available ?? []" :key="o" :label="`ASR · ${o}`" :value="o" />
          </el-select>
          <el-select v-model="ocr" class="p">
            <el-option v-for="o in engines?.ocr.available ?? []" :key="o" :label="`OCR · ${o}`" :value="o" />
          </el-select>
          <el-select v-model="schemas" multiple class="p wide">
            <el-option v-for="s in ALL_SCHEMAS" :key="s" :label="`产物 · ${s}`" :value="s" />
          </el-select>
        </div>
      </el-form-item>
    </el-form>

    <p class="note">
      平台只处理你本机的文件：不留存、不下载、不分发任何第三方视频内容。
      批内同名文件会被判重复并跳过（保留第一份）。
    </p>

    <el-button type="primary" :loading="busy" @click="submit">开始解析</el-button>
  </el-card>
</template>

<style scoped>
.box { max-width: 720px; margin: 0 auto; }
.params { display: flex; gap: 8px; flex-wrap: wrap; }
.p { width: 168px; }
.wide { width: 320px; }
.drop { padding: 26px; color: #606a7b; }
.note { font-size: 12px; color: #8b95a7; line-height: 1.7; margin: 0 0 14px; }
</style>
