import 'element-plus/theme-chalk/base.css'
// ElMessage / ElMessageBox 是函数式服务，模板解析器不会替它们注入样式
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import './styles/theme.css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'

createApp(App).use(createPinia()).use(router).mount('#app')
