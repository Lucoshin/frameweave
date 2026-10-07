<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand" @click="router.push('/')">
        <img class="brand-mark" :src="brandIcon" alt="" width="40" height="40" />
        <span class="brand-name">{{ APP_NAME }}</span>
      </div>

      <nav class="primary-nav" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.path"
          class="nav-item"
          :class="{ active: activeMenu === item.path }"
          :aria-current="activeMenu === item.path ? 'page' : undefined"
          :aria-label="item.title"
          :title="item.title"
          @click="router.push(item.path)"
        >
          <el-icon :size="19"><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </button>
      </nav>

      <div class="sidebar-foot">
        <div class="local-note">
          <span class="local-dot"></span>
          <div><strong>数据留在本机</strong><small>账号环境独立保存</small></div>
        </div>
        <button
          class="nav-item"
          :title="appStore.theme === 'dark' ? '切换亮色' : '切换暗色'"
          :aria-label="appStore.theme === 'dark' ? '切换亮色' : '切换暗色'"
          @click="appStore.toggleTheme"
        >
          <el-icon :size="19"><component :is="appStore.theme === 'dark' ? Sunny : Moon" /></el-icon>
          <span>{{ appStore.theme === 'dark' ? '切换亮色' : '切换暗色' }}</span>
        </button>
        <button class="nav-item" :class="{ active: activeMenu === '/settings' }" title="设置" aria-label="设置" :aria-current="activeMenu === '/settings' ? 'page' : undefined" @click="router.push('/settings')">
          <el-icon :size="19"><Setting /></el-icon><span>设置</span>
        </button>
      </div>
    </aside>

    <section class="workspace">
      <main class="page-stage">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" :key="$route.path" />
          </transition>
        </router-view>
      </main>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  HomeFilled, User, Picture, VideoCamera, EditPen,
  Upload, Clock, Setting, Sunny, Moon,
} from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import { APP_NAME } from '@/config/app'

const brandIcon = `${import.meta.env.BASE_URL}brand/frameweave.png`

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const navItems = [
  { path: '/', icon: HomeFilled, title: '工作台' },
  { path: '/account-management', icon: User, title: '账号' },
  { path: '/material-management', icon: Picture, title: '素材' },
  { path: '/video-workshop', icon: VideoCamera, title: '视频工坊' },
  { path: '/copywriting', icon: EditPen, title: '文案' },
  { path: '/publish-center', icon: Upload, title: '发布任务' },
  { path: '/publish-history', icon: Clock, title: '任务记录' },
]

const activeMenu = computed(() => route.path)
</script>

<style lang="scss" scoped>
.app-shell {
  display: flex;
  height: 100vh;
  color: var(--text-primary);
  background: radial-gradient(circle at 68% -10%, rgba(91, 148, 255, 0.13), transparent 32%), var(--bg-base);
}
.sidebar {
  width: 214px;
  padding: 24px 14px 16px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-light);
  box-shadow: 10px 0 42px rgba(35, 52, 85, 0.04);
  backdrop-filter: blur(22px);
}
.brand { height: 52px; padding: 0 12px; display: flex; align-items: center; gap: 11px; cursor: pointer; }
.brand-mark { width: 40px; height: 40px; display: block; flex-shrink: 0; object-fit: contain; }
.brand-name { font-size: 20px; font-weight: 720; letter-spacing: -.03em; }
.primary-nav { display: grid; gap: 5px; margin-top: 26px; }
.nav-item {
  position: relative; width: 100%; height: 45px; padding: 0 13px; display: flex; align-items: center; gap: 12px;
  border: 0; border-radius: 13px; color: var(--text-secondary); background: transparent; font-size: 14px; cursor: pointer; transition: 180ms ease;
}
.nav-item:hover { color: var(--text-primary); background: var(--bg-hover); }
.nav-item.active { color: var(--accent); background: var(--surface-active); box-shadow: 0 7px 22px rgba(35,52,85,.07); font-weight: 650; }
.nav-item.active::before { content: ''; position: absolute; left: -14px; width: 4px; height: 24px; border-radius: 0 4px 4px 0; background: var(--accent); }
.sidebar-foot { margin-top: auto; display: grid; gap: 8px; }
.local-note { margin: 0 8px 8px; padding: 12px 10px; display: flex; align-items: flex-start; gap: 9px; border: 1px solid var(--border); border-radius: 14px; background: var(--bg-elevated); }
.local-note strong, .local-note small { display: block; }.local-note strong { font-size: 12px; font-weight: 650; }.local-note small { margin-top: 3px; color: var(--text-muted); font-size: 10px; }
.local-dot { width: 7px; height: 7px; margin-top: 4px; border-radius: 50%; background: #31bd70; box-shadow: 0 0 0 4px rgba(49,189,112,.12); }
.workspace { min-width: 0; flex: 1; display: flex; flex-direction: column; }
.page-stage { flex: 1; margin: 14px 14px 14px 0; padding: 28px; overflow: auto; border: 1px solid var(--border-light); border-radius: 22px; background: var(--bg-stage); box-shadow: 0 18px 60px rgba(34,49,79,.08); backdrop-filter: blur(20px); }
.page-enter-active, .page-leave-active { transition: opacity 140ms ease, transform 140ms ease; }.page-enter-from { opacity: 0; transform: translateY(5px); }.page-leave-to { opacity: 0; transform: translateY(-3px); }
@media (max-width: 1180px) { .sidebar { width: 80px; align-items: center; }.brand { padding: 0; }.brand-name, .nav-item span, .local-note { display: none; }.nav-item { width: 48px; justify-content: center; padding: 0; } }
</style>
