<template>
  <div class="dashboard">
    <div class="dashboard-grid">
      <div class="main-column">
        <section class="panel account-health">
          <div class="panel-heading">
            <div><span class="panel-label">账号健康概览</span><h2>{{ healthTitle }}</h2></div>
            <div class="panel-actions"><button class="refresh" :disabled="loading" @click="fetchDashboardData"><el-icon :class="{ spinning: loading }"><Refresh /></el-icon>刷新状态</button><button class="text-link" @click="router.push('/account-management')">管理账号 <el-icon><ArrowRight /></el-icon></button></div>
          </div>
          <div v-if="accountStore.accounts.length" class="platform-strip">
            <div v-for="platform in activePlatforms" :key="platform.name" class="platform-item">
              <img v-if="platform.logo" :src="platform.logo" :alt="platform.name" />
              <span v-else class="platform-letter">{{ platform.name.slice(0, 1) }}</span>
              <strong>{{ platform.count }}</strong><small>{{ platform.name }}</small>
            </div>
          </div>
          <div v-else class="empty-inline">暂无账号。添加后会在这里显示真实登录状态。</div>
          <div class="status-legend"><span><i class="ok"></i>{{ accountStats.normal }} 正常</span><span><i class="warn"></i>{{ accountStats.unknown }} 待检查</span><span><i class="danger"></i>{{ accountStats.abnormal }} 异常</span></div>
        </section>

        <section class="metric-grid">
          <article><span>待人工确认</span><strong>—</strong><small>发布前安全闸门</small></article>
          <article><span>进行中任务</span><strong>—</strong><small>接入任务接口后显示</small></article>
          <article><span>账号总数</span><strong>{{ accountStats.total }}</strong><small>来自本地账号库</small></article>
          <article><span>素材总量</span><strong>{{ contentStats.total.toLocaleString() }}</strong><small>{{ contentStats.videos }} 视频 · {{ contentStats.images }} 图片</small></article>
        </section>

        <section class="panel workflow-panel">
          <div class="panel-heading"><div><span class="panel-label">工作流队列</span><h3>半自动发布 · 需人工确认</h3></div></div>
          <div class="workflow">
            <button class="workflow-step" @click="router.push('/material-management')"><b>01</b><span>素材准备<small>{{ contentStats.total ? '素材可用' : '等待添加素材' }}</small></span></button><el-icon><ArrowRight /></el-icon>
            <button class="workflow-step" @click="router.push('/video-workshop')"><b>02</b><span>内容处理<small>剪辑 · 拆分 · 混剪</small></span></button><el-icon><ArrowRight /></el-icon>
            <button class="workflow-step" @click="router.push('/copywriting')"><b>03</b><span>文案生成<small>批量 Word 模板</small></span></button><el-icon><ArrowRight /></el-icon>
            <button class="workflow-step attention" @click="router.push('/publish-center')"><b>04</b><span>任务发布<small>停在人工确认</small></span></button>
          </div>
          <div class="safety-note"><el-icon><WarningFilled /></el-icon>自动填充完成后任务会暂停，检查内容后再由你手动发布。</div>
        </section>
      </div>

      <aside class="side-column">
        <section class="panel recent-panel">
          <div class="panel-heading"><div><span class="panel-label">最近任务</span><h3>尚无可展示任务</h3></div></div>
          <div class="empty-task"><span class="empty-orbit"><el-icon><Document /></el-icon></span><p>创建发布任务后，真实进度会出现在这里。</p><button @click="router.push('/publish-center')">开始新任务</button></div>
        </section>
        <section class="panel environment-panel">
          <div class="environment-icon"><el-icon><Monitor /></el-icon></div>
          <div><span class="panel-label">浏览器登录环境</span><h3>{{ accountStats.total }} 个账号环境</h3><p>每个账号独立保存登录信息，不共用 Cookie 与站点存储。</p></div>
          <button @click="router.push('/account-management')">打开账号管理</button>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Document, Monitor, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { accountApi, materialsApi } from '@/api'
import { platformList } from '@/config/platforms'

const router = useRouter()
const accountStore = useAccountStore()
const appStore = useAppStore()
const loading = ref(false)
const accountStats = computed(() => {
  const accounts = accountStore.accounts
  return { total: accounts.length, normal: accounts.filter((item) => item.status === '正常').length, abnormal: accounts.filter((item) => item.status === '异常').length, unknown: accounts.filter((item) => !['正常', '异常'].includes(item.status)).length }
})
const healthTitle = computed(() => accountStats.value.total ? `${accountStats.value.normal} 个账号状态正常` : '等待添加第一个账号')
const activePlatforms = computed(() => platformList.map((platform) => ({ name: platform.name, logo: platform.logo, count: accountStore.accounts.filter((item) => item.platform === platform.name).length })).filter((platform) => platform.count > 0).slice(0, 7))
const contentStats = computed(() => {
  const materials = appStore.materials
  return { total: materials.length, videos: materials.filter((item) => item.file_type === 'video').length, images: materials.filter((item) => item.file_type === 'image').length }
})
async function fetchDashboardData() {
  loading.value = true
  const [accountResult, materialResult] = await Promise.allSettled([accountApi.getAccounts(), materialsApi.list({ page_size: 200 })])
  if (accountResult.status === 'fulfilled' && accountResult.value.code === 200) accountStore.setAccounts(accountResult.value.data)
  if (materialResult.status === 'fulfilled' && materialResult.value.code === 200) appStore.setMaterials(materialResult.value.data.items || [])
  loading.value = false
}
onMounted(fetchDashboardData)
</script>

<style lang="scss" scoped>
.dashboard { max-width: 1440px; margin: auto; color: var(--text-primary); }

.panel-label { color:var(--text-muted);font-size:10px;font-weight:720;letter-spacing:.12em;text-transform:uppercase }
 button{font:inherit}

.panel-actions{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:12px}
.refresh{height:38px;padding:0 14px;display:inline-flex;align-items:center;gap:7px;border:1px solid var(--border);border-radius:12px;color:var(--text-secondary);background:var(--bg-elevated);cursor:pointer}
.spinning{animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}
}

.dashboard-grid{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:16px}
.main-column,.side-column{display:grid;align-content:start;gap:16px}
.panel,.metric-grid article{border:1px solid var(--border);background:var(--bg-elevated);box-shadow:var(--shadow-card)}
.panel{padding:22px;border-radius:20px}
.panel-heading{display:flex;align-items:flex-start;justify-content:space-between}
.panel-heading h2,.panel-heading h3{margin:6px 0 0;color:var(--text-primary);letter-spacing:-.025em}
.panel-heading h2{font-size:25px}
.panel-heading h3{font-size:16px}
.text-link{display:inline-flex;align-items:center;gap:4px;border:0;color:var(--accent);background:none;cursor:pointer;font-size:12px}

.platform-strip{min-height:93px;padding:14px 0 4px;display:flex;align-items:center;gap:11px;overflow-x:auto}
.platform-item{min-width:76px;display:grid;justify-items:center;gap:4px}
.platform-item img,.platform-letter{width:42px;height:42px;display:grid;place-items:center;object-fit:contain;border-radius:13px;background:var(--bg-inset);box-shadow:inset 0 0 0 1px var(--border)}
.platform-item strong{font-size:14px}
.platform-item small{color:var(--text-muted);font-size:10px}
.empty-inline{min-height:86px;display:grid;place-items:center;color:var(--text-muted);font-size:12px}
.status-legend{display:flex;gap:18px;padding-top:12px;border-top:1px solid var(--border);color:var(--text-secondary);font-size:11px}
.status-legend span{display:inline-flex;align-items:center;gap:6px}
.status-legend i{width:7px;height:7px;border-radius:50%}
.ok{background:#39bd70}
.warn{background:#f1a33b}
.danger{background:#ed615d}

.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.metric-grid article{min-width:0;padding:17px 18px;border-radius:17px}
.metric-grid span,.metric-grid small{display:block;color:var(--text-muted);font-size:10px}
.metric-grid strong{display:block;margin:5px 0 2px;color:var(--text-primary);font-size:27px;letter-spacing:-.04em}
.workflow-panel{overflow:hidden}
.workflow{padding:20px 0 15px;display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;align-items:center;gap:7px}
.workflow>.el-icon{color:var(--text-muted)}
.workflow-step{min-width:0;min-height:78px;padding:13px;display:flex;align-items:flex-start;gap:10px;text-align:left;border:1px solid var(--border);border-radius:14px;color:var(--text-primary);background:var(--bg-inset);cursor:pointer;transition:160ms ease}
.workflow-step:hover{transform:translateY(-2px);box-shadow:0 9px 24px var(--border)}
.workflow-step b{color:var(--accent);font-size:10px}
.workflow-step span{font-size:12px;font-weight:650}
.workflow-step small{margin-top:7px;display:block;color:var(--text-muted);font-size:9px;font-weight:500}
.workflow-step.attention{border-color:rgba(231,92,82,.35);background:color-mix(in srgb, #e05a53 5%, var(--bg-elevated))}
.workflow-step.attention b,.workflow-step.attention small{color:var(--status-danger)}
.safety-note{padding:10px 12px;display:flex;align-items:center;gap:8px;border-radius:11px;color:var(--status-danger);background:rgba(238,91,83,.08);font-size:10px}

.recent-panel{min-height:347px}
.empty-task{min-height:250px;display:grid;place-items:center;align-content:center;gap:10px;text-align:center}
.empty-orbit{width:52px;height:52px;display:grid;place-items:center;border-radius:18px;color:var(--accent);background:var(--surface-active);box-shadow:0 0 0 9px rgba(36,120,248,.045)}
.empty-task p{max-width:190px;margin:4px 0;color:var(--text-muted);font-size:11px;line-height:1.6}
.empty-task button,.environment-panel button{height:34px;padding:0 13px;border:0;border-radius:10px;color:var(--accent);background:var(--surface-active);cursor:pointer;font-size:11px;font-weight:650}
.environment-panel{display:grid;grid-template-columns:auto 1fr;gap:13px}
.environment-icon{width:42px;height:42px;display:grid;place-items:center;border-radius:13px;color:var(--accent);background:var(--surface-active)}
.environment-panel h3{margin:4px 0;font-size:15px}
.environment-panel p{margin:0;color:var(--text-muted);font-size:10px;line-height:1.55}
.environment-panel button{grid-column:1/-1}

@media(max-width:1260px){.dashboard-grid{grid-template-columns:1fr}
.side-column{grid-template-columns:1fr 1fr}
.metric-grid{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:820px){.workflow{grid-template-columns:1fr 1fr}
.workflow>.el-icon{display:none}
.side-column{grid-template-columns:1fr}
}

</style>
