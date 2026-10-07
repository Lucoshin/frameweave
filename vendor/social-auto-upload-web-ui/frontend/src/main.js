import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import pinia from './stores'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import './styles/index.scss'
import './styles/original-system.scss'
import { APP_FULL_NAME } from './config/app'
import { useAppStore } from './stores/app'

document.title = APP_FULL_NAME

const app = createApp(App)

// 注册 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(router)
app.use(pinia)
app.use(ElementPlus, { locale: zhCn })

// 应用持久化的主题（mount 前执行，避免首屏闪烁）
useAppStore().loadTheme()

app.mount('#app')
