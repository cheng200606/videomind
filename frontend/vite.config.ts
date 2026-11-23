import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig } from 'vitest/config'

const api = process.env.VMIND_API ?? 'http://localhost:8000'
const proxy = {
  '/api': { target: api, changeOrigin: true },
  '/media': { target: api, changeOrigin: true }
}

export default defineConfig({
  plugins: [
    vue(),
    // 按需注册模板里的 el-* 组件并注入对应 CSS，替代全量 Element Plus。
    // vitest 直接跑 Node，不处理组件 CSS；单测里保持组件未注册即可（只断言文本/逻辑）。
    ...(process.env.VITEST ? [] : [Components({
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
      dts: 'src/components.d.ts'
    })])
  ],
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
