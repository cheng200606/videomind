import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

const api = process.env.VMIND_API ?? 'http://localhost:8000'
const proxy = {
  '/api': { target: api, changeOrigin: true },
  '/media': { target: api, changeOrigin: true }
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  server: { port: 5173, proxy },
  // 容器里用 vite preview 出图，代理规则要再声明一次才生效
  preview: { port: 5173, host: true, proxy },
  test: {
    // 组件挂载需要 DOM；vitest 会读这里的 test 字段
    environment: 'jsdom'
  }
})
