<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { getEngines, getModelSettings, setEngines, setModelSettings, testModelSettings } from '../api/client'
import { ARTIFACT_LABEL } from '../api/labels'
import type { EngineSettings, ModelProvider, ModelSettings, ModelSettingsInput, ModelTestResult } from '../api/types'

const ALL_SCHEMAS = ['summary', 'key_points', 'uml_draft', 'code_blocks']
const PROVIDERS: { value: ModelProvider; label: string }[] = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'custom', label: '自定义 OpenAI 兼容接口' }
]
const PRESETS: Record<ModelProvider, { base_url: string; model: string }> = {
  deepseek: { base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  custom: { base_url: '', model: '' }
}

const loading = ref(true)
const loadError = ref('')
const modelMeta = ref<ModelSettings | null>(null)
const engineMeta = ref<EngineSettings | null>(null)

const provider = ref<ModelProvider>('deepseek')
const baseUrl = ref('')
const modelName = ref('')
const apiKey = ref('')
const saving = ref(false)
const testing = ref(false)
const testResult = ref<ModelTestResult | null>(null)

const asr = ref('mock')
const ocr = ref('none')
const schemas = ref<string[]>([])
const savingEngines = ref(false)

const sourceLabel = computed(() => ({
  saved: '本机设置',
  env: '环境变量',
  default: '未配置'
}[modelMeta.value?.source ?? 'default']))
const sourceType = computed(() => ({ saved: 'success', env: 'warning', default: 'info' }[modelMeta.value?.source ?? 'default'] as 'success' | 'warning' | 'info'))
const hasKey = computed(() => modelMeta.value?.has_key === true)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [m, e] = await Promise.all([getModelSettings(), getEngines()])
    modelMeta.value = m
    provider.value = m.provider
    baseUrl.value = m.base_url
    modelName.value = m.model
    apiKey.value = ''
    engineMeta.value = e
    asr.value = e.asr.current
    ocr.value = e.ocr.current
    schemas.value = e.output_schemas.filter((s) => s in ARTIFACT_LABEL)
    if (!schemas.value.length) schemas.value = [...ALL_SCHEMAS]
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function onProviderChange() {
  const preset = PRESETS[provider.value]
  baseUrl.value = preset.base_url
  modelName.value = preset.model
  testResult.value = null
}

async function saveModel() {
  if (!baseUrl.value.trim() || !modelName.value.trim()) {
    ElMessage.warning('请填写 Base URL 与模型名')
    return
  }
  saving.value = true
  try {
    const body: ModelSettingsInput = {
      provider: provider.value,
      base_url: baseUrl.value.trim(),
      model: modelName.value.trim()
    }
    if (apiKey.value.trim()) body.api_key = apiKey.value.trim()
    modelMeta.value = await setModelSettings(body)
    apiKey.value = ''
    ElMessage.success('模型配置已保存')
  } catch (err) {
    ElMessage.error(`保存失败：${err instanceof Error ? err.message : err}`)
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await testModelSettings()
    if (testResult.value.ok) ElMessage.success('连接成功')
    else ElMessage.warning('连接失败，请查看下方原因')
  } catch (err) {
    ElMessage.error(`测试失败：${err instanceof Error ? err.message : err}`)
  } finally {
    testing.value = false
  }
}

async function clearKey() {
  try {
    await ElMessageBox.confirm('清除本机保存的 API Key？清除后解析将走规则兜底，直到重新配置。', '清除 Key', {
      type: 'warning', confirmButtonText: '清除', cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    modelMeta.value = await setModelSettings({
      provider: provider.value,
      base_url: baseUrl.value.trim() || PRESETS[provider.value].base_url,
      model: modelName.value.trim() || PRESETS[provider.value].model,
      clear_api_key: true
    })
    apiKey.value = ''
    testResult.value = null
    ElMessage.success('Key 已清除')
  } catch (err) {
    ElMessage.error(`清除失败：${err instanceof Error ? err.message : err}`)
  }
}

async function saveEngines() {
  if (!schemas.value.length) {
    ElMessage.warning('至少保留一种产物类型')
    return
  }
  savingEngines.value = true
  try {
    engineMeta.value = await setEngines({ asr: asr.value, ocr: ocr.value, output_schemas: schemas.value })
    ElMessage.success('解析引擎设置已保存')
  } catch (err) {
    ElMessage.error(`保存失败：${err instanceof Error ? err.message : err}`)
  } finally {
    savingEngines.value = false
  }
}
</script>

<template>
  <div class="settings">
    <div class="head">
      <div>
        <h2>设置</h2>
        <p class="sub">模型与解析引擎均为本机配置；识别结果仅供参考。</p>
      </div>
      <el-button size="small" @click="load">重新加载</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated />
    <el-alert v-else-if="loadError" type="error" :closable="false" show-icon :title="`设置加载失败：${loadError}`" />

    <template v-else>
      <el-card shadow="never" class="card">
        <template #header>
          <div class="card-head">
            <b>大模型</b>
            <div class="tags">
              <el-tag size="small" :type="sourceType">{{ sourceLabel }}</el-tag>
              <el-tag size="small" :type="hasKey ? 'success' : 'info'">{{ hasKey ? 'Key 已配置' : 'Key 未配置' }}</el-tag>
            </div>
          </div>
        </template>

        <el-form label-position="top" class="form">
          <el-form-item label="提供方">
            <el-select v-model="provider" class="field" @change="onProviderChange">
              <el-option v-for="p in PROVIDERS" :key="p.value" :label="p.label" :value="p.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="Base URL">
            <el-input v-model="baseUrl" class="field" placeholder="https://api.deepseek.com/v1" />
            <p class="hint">需为 OpenAI 兼容接口，通常以 /v1 结尾；远程地址必须使用 HTTPS，仅本机调试允许 HTTP。</p>
          </el-form-item>
          <el-form-item label="模型名">
            <el-input v-model="modelName" class="field" placeholder="deepseek-chat / gpt-4o-mini / 自定义模型名" />
          </el-form-item>
          <el-form-item label="API Key">
            <el-input
              v-model="apiKey"
              class="field"
              type="password"
              show-password
              :placeholder="hasKey ? '已配置，留空表示保持不变' : '粘贴你的 API Key'"
            />
            <p class="hint">Key 只保存在本机 backend/data/model_settings.json，不会上传或写入仓库；接口不会回显明文。</p>
          </el-form-item>
        </el-form>

        <div class="actions">
          <el-button type="primary" :loading="saving" @click="saveModel">保存配置</el-button>
          <el-button :loading="testing" :disabled="!hasKey" @click="testConnection">测试连接</el-button>
          <el-button :disabled="!hasKey" @click="clearKey">清除 Key</el-button>
        </div>

        <el-alert
          v-if="testResult"
          class="result"
          :type="testResult.ok ? 'success' : 'error'"
          :closable="false"
          show-icon
          :title="testResult.ok ? `连接成功 · ${testResult.model} · ${testResult.latency_ms}ms` : `连接失败：${testResult.error ?? '未知错误'}`"
        >
          <div v-if="testResult.ok && testResult.message">{{ testResult.message }}</div>
        </el-alert>
        <p v-if="!hasKey" class="hint warn">未配置 Key 时解析仍可完成，但结构化阶段会使用规则兜底，质量有限。</p>
      </el-card>

      <el-card shadow="never" class="card">
        <template #header><b>解析引擎</b></template>
        <p class="hint">这些是全局默认值，新建批次时生效；上传页会显示当前摘要。</p>
        <el-form label-position="top" class="form">
          <el-form-item label="ASR 引擎">
            <el-select v-model="asr" class="field">
              <el-option v-for="o in engineMeta?.asr.available ?? []" :key="o" :label="o" :value="o" />
            </el-select>
          </el-form-item>
          <el-form-item label="OCR 引擎">
            <el-select v-model="ocr" class="field">
              <el-option v-for="o in engineMeta?.ocr.available ?? []" :key="o" :label="o" :value="o" />
            </el-select>
          </el-form-item>
          <el-form-item label="默认产物集">
            <el-select v-model="schemas" multiple class="field">
              <el-option v-for="s in ALL_SCHEMAS" :key="s" :label="ARTIFACT_LABEL[s] ?? s" :value="s" />
            </el-select>
            <p class="hint">至少保留一种；未生成的产物 tab 会显示空态。</p>
          </el-form-item>
        </el-form>
        <div class="actions">
          <el-button type="primary" :loading="savingEngines" @click="saveEngines">保存解析引擎</el-button>
        </div>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.settings { max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.head h2 { margin: 0 0 4px; }
.sub { margin: 0; color: var(--vm-muted, #5f6b7d); font-size: 13px; }
.card { border-radius: 8px; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }
.form { max-width: 620px; }
.field { width: 100%; }
.hint { margin: 6px 0 0; color: var(--vm-muted, #5f6b7d); font-size: 12px; line-height: 1.6; }
.hint.warn { color: #b45309; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.result { margin-top: 12px; }
@media (max-width: 800px) {
  .settings { padding: 0; }
  .actions :deep(.el-button) { flex: 1 1 auto; }
}
</style>
