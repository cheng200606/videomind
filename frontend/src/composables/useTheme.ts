import { ref, watchEffect } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'vm-theme'

function readStored(): ThemeMode {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'   // 隐私模式等 localStorage 不可用场景
  }
}

/** 模块级单例：main.ts 导入即应用（挂载前切类，避免首帧闪白） */
const mode = ref<ThemeMode>(readStored())

watchEffect(() => {
  document.documentElement.classList.toggle('dark', mode.value === 'dark')
})

export function useThemeMode() {
  function setMode(m: ThemeMode) {
    mode.value = m
    try {
      localStorage.setItem(STORAGE_KEY, m)
    } catch {
      /* 持久化失败只影响下次启动的默认值 */
    }
  }
  return { mode, setMode }
}
