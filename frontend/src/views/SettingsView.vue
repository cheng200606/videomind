<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { getEngines, getModelSettings, setEngines, setModelSettings, testModelSettings } from '../api/client'
import { ARTIFACT_LABEL, ASR_LABEL, OCR_LABEL } from '../api/labels'
import type { EngineSettings, ModelProvider, ModelSettings, ModelSettingsInput, ModelTestResult } from '../api/types'
import { useLeaveGuard } from '../composables/useLeaveGuard'
import { useThemeMode } from '../composables/useTheme'
import PageHeader from '../components/PageHeader.vue'
import type { AppInfo, UpdateState } from '../desktop'

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
const clearing = ref(false)
const testResult = ref<ModelTestResult | null>(null)

const asr = ref('mock')
const ocr = ref('none')
const schemas = ref<string[]>([])
const savingEngines = ref(false)

// v0.13：外观（亮/暗）——useTheme 模块级单例已在挂载前应用过一次，这里只提供开关
const { mode: themeMode, setMode: setThemeMode } = useThemeMode()

function toggleDark(v: string | number | boolean) {
  setThemeMode(v ? 'dark' : 'light')
}

const desktop = typeof window !== 'undefined' ? window.videomind : undefined
const appInfo = ref<AppInfo | null>(null)
const updateState = ref<UpdateState | null>(null)
const checkingUpdate = ref(false)
let unsubscribeUpdate: (() => void) | undefined

const sourceLabel = computed(() => ({
  saved: '本机设置',
  env: '环境变量',
  default: '未配置'
}[modelMeta.value?.source ?? 'default']))
const sourceType = computed(() => ({ saved: 'success', env: 'warning', default: 'info' }[modelMeta.value?.source ?? 'default'] as 'success' | 'warning' | 'info'))
const hasKey = computed(() => modelMeta.value?.has_key === true)
const resolvedAsr = computed(() => engineMeta.value?.asr.resolved ?? engineMeta.value?.asr.current ?? '')
const usingMock = computed(() => resolvedAsr.value === 'mock')
const modelDirty = computed(() => {
  const saved = modelMeta.value
  return !!saved && (provider.value !== saved.provider || baseUrl.value !== saved.base_url
    || modelName.value !== saved.model || apiKey.value.trim() !== '')
})
const engineDirty = computed(() => {
  const saved = engineMeta.value
  return !!saved && (asr.value !== saved.asr.current || ocr.value !== saved.ocr.current
    || schemas.value.join(',') !== saved.output_schemas.join(','))
})
useLeaveGuard(() => modelDirty.value || engineDirty.value)

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

const updateAlert = computed<{ type: 'info' | 'warning' | 'success' | 'error'; title: string; description?: string }>(() => {
  const s = updateState.value
  if (!s || s.status === 'idle') return { type: 'info', title: '尚未检查更新' }
  if (s.status === 'checking') return { type: 'info', title: '正在检查更新…' }
  if (s.status === 'available') {
    return {
      type: 'warning',
      title: `发现新版本 v${s.latestVersion ?? '—'}（当前 v${s.currentVersion}）`,
      description: [s.releaseName, s.releaseNotes].filter(Boolean).join('\n')
    }
  }
  if (s.status === 'up-to-date') return { type: 'success', title: `已是最新版本 v${s.currentVersion}` }
  if (s.status === 'downloading') return { type: 'info', title: `正在下载 v${s.latestVersion ?? '—'}…` }
  if (s.status === 'downloaded') return { type: 'success', title: `v${s.latestVersion ?? '—'} 已下载，重启应用完成安装` }
  if (s.status === 'unsupported') return { type: 'info', title: '当前模式不支持自动更新', description: s.error }
  return { type: 'error', title: '检查更新失败', description: s.error ?? '未知错误' }
})

async function loadDesktop() {
  if (!desktop) return
  try {
    appInfo.value = await desktop.getAppInfo()
    updateState.value = await desktop.getUpdateState()
    unsubscribeUpdate = desktop.onUpdateState((state) => {
      updateState.value = state
      if (state.status !== 'checking') checkingUpdate.value = false
    })
  } catch (err) {
    ElMessage.error(`桌面信息读取失败：${err instanceof Error ? err.message : err}`)
  }
}
onMounted(loadDesktop)
onBeforeUnmount(() => unsubscribeUpdate?.())

async function checkUpdate() {
  if (!desktop) return
  checkingUpdate.value = true
  try {
    updateState.value = await desktop.checkForUpdates()
  } catch (err) {
    ElMessage.error(`检查更新失败：${err instanceof Error ? err.message : err}`)
  } finally {
    checkingUpdate.value = false
  }
}

async function downloadUpdate() {
  if (!desktop) return
  try {
    updateState.value = await desktop.downloadUpdate()
    if (updateState.value?.status === 'error') ElMessage.error(updateState.value.error ?? '下载失败')
  } catch (err) {
    ElMessage.error(`下载更新失败：${err instanceof Error ? err.message : err}`)
  }
}

async function installUpdate() {
  if (!desktop) return
  try {
    const r = await desktop.installUpdate()
    if (!r.ok) ElMessage.warning('更新尚未下载完成')
  } catch (err) {
    ElMessage.error(`重启安装失败：${err instanceof Error ? err.message : err}`)
  }
}

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
  const saved = modelMeta.value
  if (!saved) return
  clearing.value = true
  try {
    // 只清 Key，不把表单里尚未保存的 provider/base_url/model 顺带落盘
    modelMeta.value = await setModelSettings({
      provider: saved.provider,
      base_url: saved.base_url,
      model: saved.model,
      clear_api_key: true
    })
    apiKey.value = ''
    testResult.value = null
    ElMessage.success('Key 已清除')
  } catch (err) {
    ElMessage.error(`清除失败：${err instanceof Error ? err.message : err}`)
  } finally {
    clearing.value = false
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
    <PageHeader title="设置" subtitle="模型与解析引擎均为本机配置；识别结果仅供参考。">
      <template #actions>
        <el-button size="small" @click="load">重新加载</el-button>
      </template>
    </PageHeader>

    <el-skeleton v-if="loading" :rows="8" animated />
    <el-alert v-else-if="loadError" type="error" :closable="false" show-icon :title="`设置加载失败：${loadError}`">
      <el-button size="small" @click="load">重试</el-button>
    </el-alert>

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
          <el-button :disabled="!hasKey" :loading="clearing" @click="clearKey">清除 Key</el-button>
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

      <el-card v-if="desktop" shadow="never" class="card">
        <template #header>
          <div class="card-head">
            <b>应用更新</b>
            <el-tag size="small">当前 v{{ appInfo?.version ?? updateState?.currentVersion ?? '—' }}</el-tag>
          </div>
        </template>
        <p class="hint">从 GitHub Releases 检查新版本；下载完成后可选择立即重启安装。桌面版才提供此项。</p>
        <div class="actions">
          <el-button :loading="checkingUpdate" @click="checkUpdate">检查更新</el-button>
          <el-button
            v-if="updateState?.status === 'available'"
            type="primary"
            @click="downloadUpdate"
          >下载更新</el-button>
          <el-button
            v-if="updateState?.status === 'downloaded'"
            type="success"
            @click="installUpdate"
          >重启并安装</el-button>
        </div>
        <el-progress
          v-if="updateState?.status === 'downloading'"
          class="result"
          :percentage="Math.round(updateState.progress ?? 0)"
        />
        <el-alert
          class="result"
          :type="updateAlert.type"
          :closable="false"
          show-icon
          :title="updateAlert.title"
        >
          <div v-if="updateAlert.description" class="release-notes">{{ updateAlert.description }}</div>
        </el-alert>
      </el-card>

      <el-card shadow="never" class="card">
        <template #header>
          <div class="card-head">
            <b>解析引擎</b>
            <el-tag v-if="engineMeta" size="small" :type="usingMock ? 'warning' : 'success'">
              当前转写：{{ ASR_LABEL[resolvedAsr] ?? resolvedAsr }}
            </el-tag>
          </div>
        </template>
        <p class="hint">这些是全局默认值，新建批次时生效；上传页会显示当前摘要。</p>
        <el-form label-position="top" class="form">
          <el-form-item label="ASR 引擎">
            <el-select v-model="asr" class="field">
              <el-option
                v-for="o in engineMeta?.asr.available ?? []"
                :key="o"
                :label="ASR_LABEL[o] ?? o"
                :value="o"
              />
            </el-select>
            <p class="hint">
              <b>自动</b>会优先使用已安装的本地真实引擎；<b>演示样例（mock）只回放内置样例，不会读取你上传的视频内容</b>。
              Whisper 首次使用会自动下载约 75MB 的 tiny 模型，下载期间转写阶段会等待。
            </p>
          </el-form-item>
          <el-form-item label="OCR 引擎">
            <el-select v-model="ocr" class="field">
              <el-option
                v-for="o in engineMeta?.ocr.available ?? []"
                :key="o"
                :label="OCR_LABEL[o] ?? o"
                :value="o"
              />
            </el-select>
            <p class="hint">
              列表只显示当前环境可用的引擎：桌面版已内置 RapidOCR 画面通道；PaddleOCR 等其他引擎需在源码环境安装
              requirements-engines.txt 后才会出现。关闭后解析只走音频转写通道。
            </p>
          </el-form-item>
          <el-form-item label="默认产物集">
            <el-select v-model="schemas" multiple class="field">
              <el-option v-for="s in ALL_SCHEMAS" :key="s" :label="ARTIFACT_LABEL[s] ?? s" :value="s" />
            </el-select>
            <p class="hint">至少保留一种；未生成的产物 tab 会显示空态。</p>
          </el-form-item>
        </el-form>
        <el-alert
          v-if="usingMock"
          type="warning"
          :closable="false"
          show-icon
          class="result"
          title="当前 ASR 是演示样例：真实视频的笔记会与内容无关。"
        >
          请把 ASR 引擎切换为「自动」或「Whisper 本地转写」后保存，再对已有批次执行「整批重跑」。
        </el-alert>
        <div class="actions">
          <el-button type="primary" :loading="savingEngines" @click="saveEngines">保存解析引擎</el-button>
        </div>
      </el-card>

      <el-card shadow="never" class="card">
        <template #header>
          <div class="card-head"><b>外观与关于</b></div>
        </template>
        <div class="about-row">
          <span>深色模式</span>
          <el-switch :model-value="themeMode === 'dark'" @update:model-value="toggleDark" aria-label="深色模式开关" />
        </div>
        <p class="hint">仅影响本机界面配色；选择会被记住，下次启动保持一致。</p>
        <template v-if="desktop">
          <div class="about-row">
            <span>当前版本</span>
            <span class="vm-num">v{{ appInfo?.version ?? '—' }}</span>
          </div>
          <p class="hint">
            VideoMind 视析 · 本地知识视频结构化 · MIT License ·
            <el-link href="https://github.com/cheng200606/videomind" target="_blank" underline="never">项目仓库</el-link>
          </p>
        </template>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.settings { max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
.about-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 13px; color: var(--vm-text, #1f2937); margin: 8px 0; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }
.form { max-width: 620px; }
.field { width: 100%; }
.hint { margin: 6px 0 0; color: var(--vm-muted, #5f6b7d); font-size: 12px; line-height: 1.6; }
.hint.warn { color: var(--vm-warning-text, #b45309); }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.result { margin-top: 12px; }
.release-notes { white-space: pre-wrap; font-size: 12px; line-height: 1.6; max-height: 180px; overflow: auto; }
@media (max-width: 900px) {
  .settings { padding: 0; }
  .actions :deep(.el-button) { flex: 1 1 auto; }
}
</style>
