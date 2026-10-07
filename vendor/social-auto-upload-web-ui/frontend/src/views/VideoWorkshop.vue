<template>
  <div class="video-deck">
    <nav class="mode-switch" aria-label="视频处理方式" role="tablist">
      <button
        role="tab"
        :aria-selected="activeMode === 'split'"
        :class="{ active: activeMode === 'split' }"
        :disabled="running"
        @click="activeMode = 'split'"
      >
        <span class="mode-number">01</span>
        <span><strong>批量分割</strong><small>长视频转素材片段</small></span>
        <el-icon><Scissor /></el-icon>
      </button>
      <button
        role="tab"
        :aria-selected="activeMode === 'compose'"
        :class="{ active: activeMode === 'compose' }"
        :disabled="running"
        @click="activeMode = 'compose'"
      >
        <span class="mode-number">02</span>
        <span><strong>随机混剪</strong><small>片段组合为新成片</small></span>
        <el-icon><MagicStick /></el-icon>
      </button>
      <button v-for="(mode, index) in animationModes" :key="mode.id" role="tab" :aria-selected="activeMode === mode.id" :class="{ active: activeMode === mode.id }" :disabled="running" @click="activeMode = mode.id">
        <span class="mode-number">0{{ index + 3 }}</span><span><strong>{{ mode.title }}</strong><small>{{ mode.description }}</small></span><el-icon><MagicStick /></el-icon>
      </button>
    </nav>

    <AnimationWorkshop v-for="mode in animationModes" v-show="activeMode === mode.id" :key="mode.id" :mode="mode.id" />
    <div v-show="activeMode === 'split' || activeMode === 'compose'" class="deck-grid">
      <main class="work-surface">
        <section class="deck-section source-section">
          <div class="section-title">
            <span class="section-index">A</span>
            <div>
              <h2>{{ activeMode === 'split' ? '导入原始视频' : '建立片段池' }}</h2>
              <p>{{ activeMode === 'split' ? '可一次加入多个视频，任务会逐个处理。' : '每条成片会从片段池中抽取不重复组合。' }}</p>
            </div>
            <span v-if="files.length" class="count-pill">{{ files.length }} 个文件</span>
          </div>

          <button v-if="!files.length" class="empty-picker" @click="chooseFiles">
            <span class="picker-mark"><el-icon><Plus /></el-icon></span>
            <strong>{{ activeMode === 'split' ? '选择一个或多个长视频' : '选择已经切好的视频片段' }}</strong>
            <small>MP4 · MOV · MKV · AVI · WebM</small>
          </button>

          <div v-else class="file-queue">
            <header>
              <span>待处理队列</span>
              <div>
                <button @click="chooseFiles"><el-icon><Plus /></el-icon>继续添加</button>
                <button @click="files = []">清空</button>
              </div>
            </header>
            <div class="file-list">
              <article v-for="(file, index) in files" :key="file">
                <span class="file-order">{{ String(index + 1).padStart(2, '0') }}</span>
                <span class="file-symbol"><el-icon><VideoPlay /></el-icon></span>
                <div><strong>{{ fileName(file) }}</strong><small>{{ file }}</small></div>
                <button aria-label="移除文件" @click="removeFile(index)"><el-icon><Close /></el-icon></button>
              </article>
            </div>
          </div>
        </section>

        <section class="deck-section settings-section">
          <div class="section-title">
            <span class="section-index">B</span>
            <div>
              <h2>{{ activeMode === 'split' ? '设置切片逻辑' : '设置组合规则' }}</h2>
              <p>参数会在开始任务前经过严格校验。</p>
            </div>
          </div>

          <template v-if="activeMode === 'split'">
            <div class="choice-grid split-modes">
              <button :class="{ selected: splitConfig.mode === 'smartScene' }" @click="splitConfig.mode = 'smartScene'">
                <span class="choice-icon"><el-icon><Aim /></el-icon></span>
                <span><strong>智能场景</strong><small>根据画面变化识别切点</small></span>
                <i></i>
              </button>
              <button :class="{ selected: splitConfig.mode === 'fixedDuration' }" @click="splitConfig.mode = 'fixedDuration'">
                <span class="choice-icon"><el-icon><Timer /></el-icon></span>
                <span><strong>固定时长</strong><small>按指定秒数稳定取片</small></span>
                <i></i>
              </button>
            </div>

            <div v-if="splitConfig.mode === 'smartScene'" class="parameter-panel">
              <div class="field-block engine-field">
                <span class="field-label">检测引擎</span>
                <div class="inline-selector">
                  <button :class="{ active: splitConfig.sceneEngine === 'content' }" @click="splitConfig.sceneEngine = 'content'">
                    <strong>Content</strong><small>画面变化明确</small>
                  </button>
                  <button :class="{ active: splitConfig.sceneEngine === 'adaptive' }" @click="splitConfig.sceneEngine = 'adaptive'">
                    <strong>Adaptive</strong><small>渐变与复杂镜头</small>
                  </button>
                </div>
              </div>
              <label class="field-block slider-field">
                <span class="field-label">检测灵敏度 <b>{{ splitConfig.sensitivity.toFixed(2) }}</b></span>
                <input v-model.number="splitConfig.sensitivity" type="range" min="0.01" max="1" step="0.01" />
                <span class="range-labels"><i>更稳健</i><i>更敏感</i></span>
              </label>
              <label class="field-block compact-field">
                <span class="field-label">最短片段</span>
                <span class="number-input"><input v-model.number="splitConfig.minimumSceneDurationSeconds" type="number" min="0.1" max="600" step="0.5" /><i>秒</i></span>
              </label>
            </div>

            <div v-else class="parameter-panel fixed-panel">
              <label class="field-block compact-field">
                <span class="field-label">每段时长</span>
                <span class="number-input"><input v-model.number="splitConfig.durationSeconds" type="number" min="1" max="600" /><i>秒</i></span>
              </label>
              <label class="field-block selection-field">
                <span class="field-label">取片方式</span>
                <select v-model="splitConfig.selection">
                  <option value="automatic">连续切完整段</option>
                  <option value="startOnly">只取开头</option>
                  <option value="startAndEnd">取开头与结尾</option>
                  <option value="startMiddleAndEnd">取开头、中间与结尾</option>
                </select>
              </label>
            </div>

            <div class="common-options">
              <label class="switch-option">
                <span><strong>输出静音片段</strong><small>移除原视频音轨</small></span>
                <input v-model="splitConfig.mute" type="checkbox" /><i></i>
              </label>
              <label class="thread-option">
                <span><strong>处理线程</strong><small>建议保留系统余量</small></span>
                <select v-model.number="splitConfig.maxThreads">
                  <option v-for="thread in 8" :key="thread" :value="thread">{{ thread }}</option>
                </select>
              </label>
            </div>
          </template>

          <template v-else>
            <div class="compose-grid">
              <label class="metric-field">
                <span class="metric-number">01</span>
                <span><strong>生成数量</strong><small>本轮输出几条成片</small></span>
                <input v-model.number="composeConfig.outputCount" type="number" min="1" :max="Math.max(1, maxUniqueCompositions)" />
              </label>
              <label class="metric-field">
                <span class="metric-number">02</span>
                <span><strong>每条片段数</strong><small>单条成片的素材数量</small></span>
                <input v-model.number="composeConfig.clipsPerOutput" type="number" min="1" max="100" />
              </label>
              <label class="metric-field">
                <span class="metric-number">03</span>
                <span><strong>并行任务</strong><small>同时编码的成片数量</small></span>
                <input v-model.number="composeConfig.maxParallelism" type="number" min="1" max="8" />
              </label>
            </div>
            <div class="compose-foot">
              <label class="switch-option">
                <span><strong>生成静音成片</strong><small>适合后续统一配音</small></span>
                <input v-model="composeConfig.muteAudio" type="checkbox" /><i></i>
              </label>
              <span class="combination-note" :class="{ warning: composeLimitMessage }">
                <el-icon><DataAnalysis /></el-icon>{{ composeLimitMessage || `当前片段池最多支持 ${maxUniqueCompositions} 种唯一组合` }}
              </span>
            </div>
          </template>
        </section>

        <section class="run-strip">
          <button class="output-picker" @click="chooseOutputDirectory">
            <span><el-icon><FolderOpened /></el-icon></span>
            <span><small>输出位置</small><strong>{{ outputDirectory || '选择保存目录' }}</strong></span>
            <el-icon><ArrowRight /></el-icon>
          </button>
          <button v-if="running" class="cancel-button" :disabled="cancelling" @click="cancelJob">
            {{ cancelling ? '正在停止…' : '停止任务' }}
          </button>
          <button v-else class="start-button" :disabled="!canStart" @click="startJob">
            <el-icon><VideoPlay /></el-icon>{{ activeMode === 'split' ? '开始分割' : '开始混剪' }}
            <el-icon><ArrowRight /></el-icon>
          </button>
        </section>

        <div v-if="errorMessage" class="error-banner" role="alert"><el-icon><WarningFilled /></el-icon><span>{{ errorMessage }}</span></div>
      </main>

      <aside class="activity-rail">
        <section class="activity-card">
          <header>
            <div><span class="eyebrow">LIVE RUN</span><h2>任务活动</h2></div>
            <span class="run-state" :class="{ active: running }"><i></i>{{ running ? '执行中' : '等待任务' }}</span>
          </header>
          <div class="progress-orbit" :style="{ '--progress': `${progressPercent * 3.6}deg` }">
            <div><strong>{{ Math.round(progressPercent) }}<small>%</small></strong><span>{{ running ? '处理中' : result ? statusText(result.status) : '未开始' }}</span></div>
          </div>
          <div v-if="activities.length" class="activity-list">
            <article v-for="(entry, index) in activities" :key="`${index}-${entry.message}`">
              <i></i><div><strong>{{ entry.message }}</strong><small>{{ entry.detail }}</small></div>
            </article>
          </div>
          <div v-else class="activity-empty"><span></span><p>任务开始后，这里会按顺序记录检测、编码与验收进度。</p></div>
        </section>

        <section class="result-card">
          <header>
            <div><span class="eyebrow">DELIVERABLES</span><h2>输出结果</h2></div>
            <span v-if="result" class="result-count">{{ successfulOutputs.length }} 个文件</span>
          </header>
          <template v-if="result">
            <div class="result-summary">
              <span class="summary-status" :class="result.status">{{ statusText(result.status) }}</span>
              <small>{{ failedItems }} 项失败</small>
            </div>
            <div class="result-items">
              <article v-for="item in result.items" :key="item.input" :class="item.status">
                <span><el-icon><component :is="item.status === 'succeeded' ? CircleCheck : Warning" /></el-icon></span>
                <div>
                  <strong>{{ resultItemName(item) }}</strong>
                  <small v-if="item.outputs.length">{{ item.outputs.length }} 个输出 · {{ item.outputs[0] }}</small>
                  <small v-else>{{ item.error || '未生成文件' }}</small>
                </div>
              </article>
            </div>
            <button v-if="activeMode === 'split' && successfulOutputs.length" class="reuse-button" @click="useOutputsForCompose">
              将本轮片段加入随机混剪<el-icon><ArrowRight /></el-icon>
            </button>
          </template>
          <div v-else class="result-empty">
            <span><el-icon><Collection /></el-icon></span>
            <strong>还没有输出</strong>
            <small>完成任务后可在这里核对每个文件和失败原因。</small>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import AnimationWorkshop from '@/components/AnimationWorkshop.vue'
import {
  Aim, ArrowRight, CircleCheck, Close, Collection, DataAnalysis, FolderOpened,
  MagicStick, Plus, Scissor, Timer, VideoPlay, Warning, WarningFilled,
} from '@element-plus/icons-vue'
import {
  createComposeJob,
  createSplitJob,
  createVideoJobId,
} from '../../../../../apps/desktop/shared/video-workshop.js'

const activeMode = ref('split')
const animationModes = [{ id: 'remotion', title: 'AI 动画', description: 'AI 分镜与动态图形' }, { id: 'illustrated', title: '图文动画', description: '图片与文字生成短片' }]
const files = ref([])
const outputDirectory = ref('')
const running = ref(false)
const cancelling = ref(false)
const currentJobId = ref('')
const activities = ref([])
const progressPercent = ref(0)
const result = ref(null)
const errorMessage = ref('')
let unsubscribeEvents = null

const splitConfig = reactive({
  mode: 'smartScene',
  sceneEngine: 'adaptive',
  sensitivity: 0.72,
  minimumSceneDurationSeconds: 3,
  durationSeconds: 10,
  selection: 'automatic',
  mute: false,
  maxThreads: 2,
})

const composeConfig = reactive({
  outputCount: 1,
  clipsPerOutput: 3,
  maxParallelism: 2,
  muteAudio: false,
})

const fileName = path => path?.split(/[\\/]/).pop() || path
const uniqueFiles = values => [...new Set(values)]

const maxUniqueCompositions = computed(() => {
  const n = files.value.length
  const k = composeConfig.clipsPerOutput
  if (!Number.isInteger(k) || k < 1 || k > n) return 0
  const smallerK = Math.min(k, n - k)
  let combinations = 1
  for (let index = 1; index <= smallerK; index += 1) {
    combinations = combinations * (n - smallerK + index) / index
    if (combinations >= 100) return 100
  }
  return Math.floor(combinations)
})

const composeLimitMessage = computed(() => {
  if (activeMode.value !== 'compose' || !files.value.length) return ''
  if (composeConfig.clipsPerOutput > files.value.length) return '片段数量少于每条成片所需数量'
  if (composeConfig.outputCount > maxUniqueCompositions.value) return '生成数量超过当前片段池可提供的唯一组合'
  return ''
})

const canStart = computed(() => {
  if (running.value || !files.value.length || !outputDirectory.value) return false
  if (activeMode.value === 'split') return true
  return !composeLimitMessage.value && composeConfig.outputCount >= 1
})

const successfulOutputs = computed(() => (
  result.value?.items?.flatMap(item => item.status === 'succeeded' ? item.outputs : []) || []
))
const failedItems = computed(() => result.value?.items?.filter(item => item.status === 'failed').length || 0)

async function chooseFiles() {
  if (!window.matrixDesktop) {
    errorMessage.value = '请在映织桌面端中选择视频文件。'
    return
  }
  const selected = await window.matrixDesktop.chooseVideoFiles()
  if (selected.length) files.value = uniqueFiles([...files.value, ...selected])
}

async function chooseOutputDirectory() {
  if (!window.matrixDesktop) {
    errorMessage.value = '请在映织桌面端中选择输出目录。'
    return
  }
  outputDirectory.value = await window.matrixDesktop.chooseOutputDirectory() || outputDirectory.value
}

function removeFile(index) {
  files.value.splice(index, 1)
}

function buildRequest(jobId) {
  if (activeMode.value === 'split') {
    return createSplitJob({
      jobId,
      inputs: files.value,
      outputDirectory: outputDirectory.value,
      ...splitConfig,
    })
  }
  return createComposeJob({
    jobId,
    clips: files.value,
    outputDirectory: outputDirectory.value,
    ...composeConfig,
  })
}

async function startJob() {
  const jobId = createVideoJobId(activeMode.value)
  currentJobId.value = jobId
  running.value = true
  cancelling.value = false
  activities.value = []
  progressPercent.value = 0
  result.value = null
  errorMessage.value = ''
  try {
    result.value = await window.matrixDesktop.startVideoJob(buildRequest(jobId))
    progressPercent.value = result.value.status === 'succeeded' ? 100 : progressPercent.value
    if (result.value.status === 'failed') errorMessage.value = result.value.error || '任务未生成有效文件。'
  } catch (error) {
    errorMessage.value = error.message || '视频任务启动失败。'
  } finally {
    running.value = false
    cancelling.value = false
  }
}

async function cancelJob() {
  cancelling.value = true
  try {
    await window.matrixDesktop.cancelVideoJob(currentJobId.value)
  } catch (error) {
    cancelling.value = false
    errorMessage.value = error.message || '停止任务失败。'
  }
}

function statusText(status) {
  return ({ succeeded: '全部完成', partial: '部分完成', failed: '处理失败', cancelled: '已停止' })[status] || '等待结果'
}

function resultItemName(item) {
  return item.input.startsWith('composition:') ? `成片 ${item.input.split(':')[1]}` : fileName(item.input)
}

function describeEvent(event) {
  const stageNames = {
    started: '任务已进入本机引擎',
    'encoder-detection': '正在检测可用编码器',
    'encoder-ready': '编码器检测完成',
    validation: '正在完整解码预检素材',
    split: '正在分析并导出片段',
    compose: '正在组合并验收成片',
  }
  return event.message || stageNames[event.stage] || '处理进度已更新'
}

function receiveJobEvent(payload) {
  if (payload.jobId !== currentJobId.value) return
  const event = payload.event
  if (typeof event.percent === 'number') progressPercent.value = Math.max(0, Math.min(100, event.percent))
  else if (event.total > 0) progressPercent.value = event.current * 100 / event.total
  activities.value.push({
    message: describeEvent(event),
    detail: event.input ? fileName(event.input) : event.stage || event.type,
  })
  if (activities.value.length > 8) activities.value.shift()
}

function useOutputsForCompose() {
  files.value = uniqueFiles(successfulOutputs.value)
  activeMode.value = 'compose'
  result.value = null
  progressPercent.value = 0
  composeConfig.clipsPerOutput = Math.min(3, files.value.length)
  composeConfig.outputCount = 1
}

onMounted(() => {
  if (window.matrixDesktop) unsubscribeEvents = window.matrixDesktop.onVideoJobEvent(receiveJobEvent)
})

onBeforeUnmount(() => {
  unsubscribeEvents?.()
})
</script>

<style scoped>
.video-deck{--mint:#2fb778;max-width:1220px;margin:auto;color:var(--text-primary);font-family:"Microsoft YaHei UI","PingFang SC",sans-serif}
.eyebrow{color:var(--text-muted);font-size:9px;font-weight:800;letter-spacing:.16em}
.run-state i{width:7px;height:7px;border-radius:50%;background:var(--mint);box-shadow:0 0 0 4px rgba(47,183,120,.1)}
.mode-switch{width:100%;box-sizing:border-box;margin-top:0;padding:4px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;border:1px solid var(--border);border-radius:17px;background:var(--bg-inset)}
.mode-switch button{min-height:58px;padding:8px 13px;display:grid;grid-template-columns:29px 1fr auto;align-items:center;gap:10px;text-align:left;border:0;border-radius:13px;color:var(--text-secondary);background:transparent;cursor:pointer;transition:.2s ease}
.mode-switch button:disabled{cursor:default}
.mode-switch button.active{color:var(--accent);background:var(--bg-elevated);box-shadow:var(--shadow-card)}
.mode-number{font:700 9px "SFMono-Regular",Consolas,monospace}
.mode-switch strong,.mode-switch small{display:block}
.mode-switch strong{font-size:12px}
.mode-switch small{margin-top:2px;color:var(--text-muted);font-size:9px}
.mode-switch .el-icon{font-size:17px}
.deck-grid{margin-top:15px;display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:16px}
.work-surface{padding:23px;border:1px solid var(--border);border-radius:22px;background:var(--bg-elevated);box-shadow:var(--shadow-card)}
.deck-section+.deck-section{margin-top:24px;padding-top:23px;border-top:1px solid var(--border)}
.section-title{display:flex;align-items:flex-start;gap:11px}
.section-title>div{min-width:0;flex:1}
.section-index{width:27px;height:27px;display:grid;place-items:center;flex:0 0 auto;border-radius:9px;color:var(--accent);background:var(--surface-active);font:800 9px "SFMono-Regular",Consolas,monospace}
.section-title h2{margin:1px 0 0;font-size:15px}
.section-title p{margin:4px 0 0;color:var(--text-muted);font-size:9px}
.count-pill{padding:5px 9px;border-radius:20px;color:var(--accent);background:var(--surface-active);font-size:9px;font-weight:750}
.empty-picker{width:100%;min-height:142px;margin-top:15px;display:grid;place-items:center;align-content:center;gap:7px;border:1.5px dashed var(--border);border-radius:17px;color:var(--text-primary);background:var(--bg-inset);cursor:pointer;transition:.2s ease}
.empty-picker:hover{border-color:var(--accent);transform:translateY(-1px)}
.picker-mark{width:40px;height:40px;display:grid;place-items:center;border-radius:13px;color:var(--accent);background:var(--surface-active);font-size:17px}
.empty-picker strong{font-size:12px}
.empty-picker small{color:var(--text-muted);font-size:9px}
.file-queue{margin-top:15px;border:1px solid var(--border);border-radius:16px;overflow:hidden;background:var(--bg-inset)}
.file-queue>header{height:39px;padding:0 12px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);color:var(--text-secondary);font-size:9px;font-weight:700}
.file-queue>header div{display:flex;gap:5px}
.file-queue>header button{height:26px;padding:0 8px;display:flex;align-items:center;gap:4px;border:0;border-radius:8px;color:var(--text-secondary);background:var(--bg-inset);font-size:8px;cursor:pointer}
.file-list{max-height:180px;overflow:auto}
.file-list article{min-height:51px;padding:8px 11px;display:grid;grid-template-columns:24px 34px minmax(0,1fr) auto;align-items:center;gap:9px;border-bottom:1px solid var(--border);background:var(--bg-elevated)}
.file-list article:last-child{border:0}
.file-order{color:var(--text-muted);font:8px "SFMono-Regular",Consolas,monospace}
.file-symbol{width:31px;height:31px;display:grid;place-items:center;border-radius:10px;color:var(--accent);background:var(--surface-active)}
.file-list strong,.file-list small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-list strong{font-size:10px}
.file-list small{max-width:560px;margin-top:3px;color:var(--text-muted);font-size:8px}
.file-list article>button{width:27px;height:27px;display:grid;place-items:center;border:0;border-radius:8px;color:var(--text-muted);background:transparent;cursor:pointer}
.file-list article>button:hover{color:var(--status-danger);background:color-mix(in srgb, #e05a53 10%, var(--bg-elevated))}
.choice-grid{margin-top:15px;display:grid;grid-template-columns:1fr 1fr;gap:10px}
.choice-grid>button{min-height:66px;padding:12px;display:grid;grid-template-columns:38px 1fr 10px;align-items:center;gap:10px;text-align:left;border:1px solid var(--border);border-radius:15px;color:var(--text-secondary);background:var(--bg-inset);cursor:pointer}
.choice-grid>button.selected{border-color:rgba(23,108,245,.3);background:var(--surface-active);box-shadow:0 0 0 3px rgba(23,108,245,.045)}
.choice-icon{width:37px;height:37px;display:grid;place-items:center;border-radius:12px;color:var(--text-secondary);background:var(--bg-inset)}
.selected .choice-icon{color:var(--accent);background:var(--surface-active)}
.choice-grid strong,.choice-grid small{display:block}
.choice-grid strong{font-size:11px}
.choice-grid small{margin-top:3px;color:var(--text-muted);font-size:8px}
.choice-grid button>i{width:8px;height:8px;border:2px solid var(--border);border-radius:50%}
.choice-grid button.selected>i{border:3px solid var(--accent)}
.parameter-panel{margin-top:11px;padding:14px;display:grid;grid-template-columns:1.25fr 1.5fr .65fr;gap:14px;border:1px solid var(--border);border-radius:15px;background:var(--bg-inset)}
.fixed-panel{grid-template-columns:.7fr 1.3fr}
.field-block{min-width:0;display:grid;align-content:start;gap:8px}
.field-label{color:var(--text-secondary);font-size:9px;font-weight:700}
.field-label b{float:right;color:var(--accent);font:700 9px "SFMono-Regular",Consolas,monospace}
.inline-selector{padding:3px;display:grid;grid-template-columns:1fr 1fr;gap:3px;border-radius:11px;background:var(--bg-inset)}
.inline-selector button{min-height:35px;padding:4px 7px;text-align:left;border:0;border-radius:8px;color:var(--text-secondary);background:transparent;cursor:pointer}
.inline-selector button.active{color:var(--accent);background:var(--bg-elevated);box-shadow:0 3px 10px var(--border)}
.inline-selector strong,.inline-selector small{display:block}
.inline-selector strong{font-size:9px}
.inline-selector small{margin-top:2px;font-size:7px}
.slider-field input{width:100%;height:4px;margin:9px 0 0;accent-color:var(--accent)}
.range-labels{display:flex;justify-content:space-between;color:var(--text-muted);font-size:7px}
.range-labels i{font-style:normal}
.number-input{height:37px;display:grid;grid-template-columns:1fr 27px;border:1px solid var(--border);border-radius:10px;background:var(--bg-elevated);overflow:hidden}
.number-input input{min-width:0;padding:0 8px;border:0;outline:0;color:var(--text-primary);background:transparent;font-size:10px}
.number-input i{display:grid;place-items:center;color:var(--text-muted);background:var(--bg-inset);font-size:8px;font-style:normal}
.selection-field select,.thread-option select{height:37px;padding:0 10px;border:1px solid var(--border);border-radius:10px;outline:0;color:var(--text-primary);background:var(--bg-elevated);font-size:9px}
.common-options,.compose-foot{margin-top:11px;padding:12px 14px;display:flex;align-items:center;justify-content:space-between;gap:15px;border:1px solid var(--border);border-radius:14px;background:var(--bg-inset)}
.switch-option,.thread-option{display:flex;align-items:center;gap:12px}
.switch-option>span,.thread-option>span{display:block}
.switch-option strong,.switch-option small,.thread-option strong,.thread-option small{display:block}
.switch-option strong,.thread-option strong{font-size:9px}
.switch-option small,.thread-option small{margin-top:2px;color:var(--text-muted);font-size:7px}
.switch-option input{position:absolute;opacity:0;pointer-events:none}
.switch-option>i{width:31px;height:18px;padding:2px;box-sizing:border-box;border-radius:12px;background:var(--border);transition:.2s}
.switch-option>i:after{content:"";width:14px;height:14px;display:block;border-radius:50%;background:var(--accent-contrast);box-shadow:0 1px 4px rgba(20,31,50,.18);transition:.2s}
.switch-option input:checked+i{background:var(--accent-solid)}
.switch-option input:checked+i:after{transform:translateX(13px)}
.thread-option select{width:58px;height:31px}
.compose-grid{margin-top:15px;display:grid;grid-template-columns:repeat(3,1fr);gap:9px}
.metric-field{min-height:72px;padding:12px;display:grid;grid-template-columns:25px 1fr 54px;align-items:center;gap:8px;border:1px solid var(--border);border-radius:14px;background:var(--bg-inset)}
.metric-number{color:var(--text-muted);font:700 8px "SFMono-Regular",Consolas,monospace}
.metric-field strong,.metric-field small{display:block}
.metric-field strong{font-size:10px}
.metric-field small{margin-top:3px;color:var(--text-muted);font-size:7px}
.metric-field input{width:54px;height:34px;padding:0 6px;box-sizing:border-box;border:1px solid var(--border);border-radius:9px;outline:0;text-align:center;color:var(--accent);background:var(--bg-elevated);font:700 11px "SFMono-Regular",Consolas,monospace}
.combination-note{display:flex;align-items:center;gap:6px;color:var(--text-secondary);font-size:8px}
.combination-note.warning{color:var(--status-warning)}
.run-strip{margin-top:23px;padding-top:19px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;border-top:1px solid var(--border)}
.output-picker{min-width:0;height:47px;padding:0 12px;display:grid;grid-template-columns:31px 1fr auto;align-items:center;gap:9px;text-align:left;border:1px solid var(--border);border-radius:13px;color:var(--text-secondary);background:var(--bg-inset);cursor:pointer}
.output-picker>span:first-child{width:30px;height:30px;display:grid;place-items:center;border-radius:9px;color:var(--accent);background:var(--surface-active)}
.output-picker small,.output-picker strong{display:block}
.output-picker small{font-size:7px}
.output-picker strong{max-width:520px;margin-top:2px;overflow:hidden;color:var(--text-primary);font-size:9px;text-overflow:ellipsis;white-space:nowrap}
.start-button,.cancel-button{height:47px;padding:0 17px;display:flex;align-items:center;justify-content:center;gap:7px;border:0;border-radius:13px;font-size:10px;font-weight:750;cursor:pointer}
.start-button{min-width:145px;color:var(--accent-contrast);background:var(--accent-solid);box-shadow:0 9px 20px rgba(23,108,245,.2)}
.start-button:disabled{opacity:.35;box-shadow:none;cursor:not-allowed}
.cancel-button{color:var(--status-danger);background:color-mix(in srgb, #e05a53 10%, var(--bg-elevated))}
.error-banner{margin-top:11px;padding:10px 12px;display:flex;align-items:flex-start;gap:8px;border-radius:11px;color:var(--status-danger);background:color-mix(in srgb, #e05a53 10%, var(--bg-elevated));font-size:9px;line-height:1.5}
.activity-rail{display:grid;align-content:start;gap:12px}
.activity-card,.result-card{padding:18px;border:1px solid var(--border);border-radius:19px;background:var(--bg-elevated);box-shadow:var(--shadow-card)}
.activity-card>header,.result-card>header{display:flex;align-items:flex-start;justify-content:space-between}
.activity-card h2,.result-card h2{margin:5px 0 0;font-size:14px}
.run-state{height:23px;padding:0 8px;display:flex;align-items:center;gap:6px;border-radius:15px;color:var(--text-muted);background:var(--bg-inset);font-size:8px;font-weight:700}
.run-state i{width:5px;height:5px;background:var(--text-muted);box-shadow:none}
.run-state.active{color:var(--status-success);background:color-mix(in srgb, #2fb778 10%, var(--bg-elevated))}
.run-state.active i{background:var(--mint);box-shadow:0 0 0 3px rgba(47,183,120,.1)}
.progress-orbit{--progress:0deg;width:118px;height:118px;margin:19px auto 14px;padding:8px;box-sizing:border-box;border-radius:50%;background:conic-gradient(var(--accent) var(--progress),var(--border) 0);box-shadow:var(--shadow-card)}
.progress-orbit>div{width:100%;height:100%;display:grid;place-items:center;align-content:center;border-radius:50%;background:var(--bg-elevated)}
.progress-orbit strong{font:750 24px "SFMono-Regular",Consolas,monospace;letter-spacing:-.08em}
.progress-orbit strong small{font-size:9px;letter-spacing:0}
.progress-orbit span{margin-top:3px;color:var(--text-muted);font-size:8px}
.activity-list{display:grid;gap:0}
.activity-list article{min-height:39px;display:grid;grid-template-columns:12px 1fr;gap:8px;position:relative}
.activity-list article>i{width:6px;height:6px;margin-top:5px;border:2px solid var(--accent);border-radius:50%;background:var(--bg-elevated);z-index:1}
.activity-list article:not(:last-child):before{content:"";width:1px;position:absolute;top:12px;bottom:-1px;left:4px;background:var(--border)}
.activity-list strong,.activity-list small{display:block}
.activity-list strong{overflow:hidden;font-size:8px;text-overflow:ellipsis;white-space:nowrap}
.activity-list small{margin-top:3px;color:var(--text-muted);font-size:7px}
.activity-empty{padding:18px 8px 5px;text-align:center}
.activity-empty span{width:38px;height:20px;margin:auto;display:block;border-top:1px solid var(--border);border-bottom:1px solid var(--border);opacity:.8}
.activity-empty p{margin:10px 0 0;color:var(--text-muted);font-size:8px;line-height:1.55}
.result-card{min-height:190px}
.result-count{padding:4px 7px;border-radius:12px;color:var(--accent);background:var(--surface-active);font-size:8px;font-weight:700}
.result-summary{margin-top:14px;display:flex;align-items:center;justify-content:space-between}
.summary-status{padding:5px 8px;border-radius:14px;color:var(--status-success);background:color-mix(in srgb, #2fb778 10%, var(--bg-elevated));font-size:8px;font-weight:750}
.summary-status.partial{color:var(--status-warning);background:color-mix(in srgb, #e9a239 10%, var(--bg-elevated))}
.summary-status.failed,.summary-status.cancelled{color:var(--status-danger);background:color-mix(in srgb, #e05a53 10%, var(--bg-elevated))}
.result-summary small{color:var(--text-muted);font-size:8px}
.result-items{max-height:170px;margin-top:9px;display:grid;gap:6px;overflow:auto}
.result-items article{padding:8px;display:grid;grid-template-columns:24px minmax(0,1fr);gap:8px;border:1px solid var(--border);border-radius:10px;background:var(--bg-inset)}
.result-items article>span{width:23px;height:23px;display:grid;place-items:center;border-radius:7px;color:var(--status-success);background:color-mix(in srgb, #2fb778 10%, var(--bg-elevated))}
.result-items article.failed>span{color:var(--status-danger);background:color-mix(in srgb, #e05a53 10%, var(--bg-elevated))}
.result-items strong,.result-items small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.result-items strong{font-size:8px}
.result-items small{max-width:220px;margin-top:3px;color:var(--text-muted);font-size:7px}
.reuse-button{width:100%;height:34px;margin-top:10px;display:flex;align-items:center;justify-content:center;gap:6px;border:0;border-radius:10px;color:var(--accent);background:var(--surface-active);font-size:8px;font-weight:700;cursor:pointer}
.result-empty{padding:28px 10px 12px;display:grid;place-items:center;text-align:center}
.result-empty>span{width:39px;height:39px;display:grid;place-items:center;border-radius:13px;color:var(--text-muted);background:var(--bg-inset);font-size:17px}
.result-empty strong{margin-top:9px;font-size:9px}
.result-empty small{max-width:210px;margin-top:4px;color:var(--text-muted);font-size:8px;line-height:1.5}
@media(max-width:1050px){.deck-grid{grid-template-columns:1fr}
.activity-rail{grid-template-columns:1fr 1fr}
.progress-orbit{width:102px;height:102px}
.parameter-panel{grid-template-columns:1fr 1fr}
.compact-field{grid-column:1/-1}
.compose-grid{grid-template-columns:1fr}
}
@media(max-width:720px){.mode-switch{grid-template-columns:repeat(2,minmax(0,1fr))}
.choice-grid,.activity-rail{grid-template-columns:1fr}
.parameter-panel,.fixed-panel{grid-template-columns:1fr}
.compact-field{grid-column:auto}
.common-options,.compose-foot{align-items:flex-start;flex-direction:column}
.run-strip{grid-template-columns:1fr}
.start-button,.cancel-button{width:100%}
.work-surface{padding:17px}
}

</style>
