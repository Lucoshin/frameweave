<template>
  <div class="animation-grid">
    <main class="animation-surface">
      <header><span class="section-number">A</span><div><h2>{{ illustrated ? '图文动画' : 'AI 动画' }}</h2><p>{{ illustrated ? '图片、文字与镜头运动，组成有节奏的图文短片。' : '描述创作要求，由 AI 编写分镜，再用动态图形生成成片。' }}</p></div></header>
      <fieldset :disabled="busy">
        <label class="field">创作要求<textarea v-model="prompt" maxlength="6000" rows="6" placeholder="例如：用三个镜头讲清一个习惯的养成方法，文字简短，节奏舒缓。" /></label>
        <div class="parameters">
          <label class="field">目标时长（秒）<input v-model.number="duration" type="number" min="6" max="120" /></label>
          <label class="field">分镜数量<input v-model.number="sceneCount" type="number" min="1" max="12" /></label>
          <label class="field">画幅<select v-model="aspectRatio"><option>9:16</option><option>16:9</option><option>1:1</option></select></label>
        </div>
        <section v-if="illustrated" class="image-section">
          <h3>画面来源</h3>
          <div class="source-options"><label><input v-model="imageSource" type="radio" value="local" /> 本地图片</label><label><input v-model="imageSource" type="radio" value="ai" /> AI 生成图片</label></div>
          <p v-if="imageSource === 'ai'">使用设置中的图片服务，生成黑底、象牙白线描与暗金点缀的插画。</p>
          <template v-else><p>按镜头顺序选择 {{ sceneCount }} 张图片；每张对应一个分镜。</p><input type="file" accept="image/png,image/jpeg,image/webp" multiple @change="selectImages" /><ol v-if="images.length"><li v-for="(file,index) in images" :key="index">{{ file.name }}</li></ol></template>
        </section>
        <section class="narration-section"><label><input v-model="narration" type="checkbox" /> 生成配音</label><p>{{ narration ? '使用设置中的语音服务及音色。按实际配音时长延长镜头，成片最长 120 秒。' : '默认生成静音视频，可开启配音或克隆音色。' }}</p></section>
      </fieldset>
      <div class="service-note"><span>文本：{{ ai.text.model || '未配置' }}<template v-if="illustrated && imageSource === 'ai'"> · 图片：{{ ai.image.model || '未配置' }}</template></span><router-link to="/settings">配置 AI 服务 →</router-link></div>
      <p class="privacy-note">分镜和配图请求发送至你配置的 AI 服务，视频在本机渲染。</p>
      <button class="generate-button" :disabled="busy || !prompt.trim()" @click="generate">{{ busy ? '正在生成…' : '生成动画' }}</button>
      <div v-if="error" class="error" role="alert">{{ error }}</div>
    </main>
    <aside class="animation-rail">
      <section class="status-card"><span class="eyebrow">LIVE RUN</span><h2>任务活动</h2><div class="progress-number">{{ job?.progress || 0 }}<small>%</small></div><progress :value="job?.progress || 0" max="100" /><p role="status">{{ submitting ? '正在上传素材并创建任务' : job?.message || '准备好内容后，开始生成' }}</p><button v-if="pollFailed" class="retry-button" @click="poll">重新检查任务</button></section>
      <section class="result-card"><span class="eyebrow">DELIVERABLES</span><h2>输出结果</h2><template v-if="job?.status === 'succeeded'"><video :src="artifactUrl(job.videoUrl)" controls preload="metadata" /><strong>{{ job.title }}</strong><p>{{ job.duration.toFixed(1) }} 秒 · MP4</p><div class="downloads"><a :href="artifactUrl(job.videoUrl) + '?download=1'">下载视频</a><a :href="artifactUrl(job.storyUrl) + '?download=1'">下载分镜</a></div></template><p v-else class="empty-output">{{ job?.status === 'failed' ? '本次生成失败，请查看原因后重试。' : '生成完成后在这里预览和下载成片。' }}</p></section>
    </aside>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { http } from '@/utils/request'
import { useAiStore } from '@/stores/ai'
const props = defineProps({ mode: { type: String, required: true } })
const ai = useAiStore()
const illustrated = computed(() => props.mode === 'illustrated')
const prompt = ref(''), duration = ref(15), sceneCount = ref(3), aspectRatio = ref('9:16')
const imageSource = ref('local'), images = ref([]), narration = ref(false)
const job = ref(null), submitting = ref(false), error = ref(''), pollFailed = ref(false)
const busy = computed(() => submitting.value || ['queued', 'running'].includes(job.value?.status))
const storageKey = `matrix-animation-job-${props.mode}`
let timer, mounted = true
const artifactUrl = path => `${import.meta.env.VITE_API_BASE_URL || ''}${path}`
const selectImages = event => { images.value = Array.from(event.target.files) }

async function poll() {
  clearTimeout(timer)
  pollFailed.value = false
  try {
    const response = await http.get(`/api/v2/animation/jobs/${job.value.id}`, undefined, { matrixSilentErrors: true })
    if (!mounted) return
    job.value = response.data
    error.value = job.value.error || ''
    if (['queued', 'running'].includes(job.value.status)) timer = setTimeout(poll, 1500)
    else sessionStorage.removeItem(storageKey)
  } catch (err) {
    if (!mounted) return
    error.value = err.message
    if (err.response?.status === 404) { job.value = null; sessionStorage.removeItem(storageKey) }
    else pollFailed.value = true
  }
}

async function generate() {
  error.value = ''
  try {
    if (!Number.isFinite(duration.value) || duration.value < 6 || duration.value > 120) throw new Error('时长应为 6–120 秒')
    if (!Number.isInteger(sceneCount.value) || sceneCount.value < 1 || sceneCount.value > 12 || duration.value / sceneCount.value < 2) throw new Error('分镜需为 1–12 个，每镜至少 2 秒')
    const payload = { mode: props.mode, prompt: prompt.value, duration: duration.value, sceneCount: sceneCount.value, aspectRatio: aspectRatio.value, imageSource: illustrated.value ? imageSource.value : 'none', textConfig: ai.getTextConfig(), assetIds: [] }
    if (narration.value) payload.narration = ai.getSpeechConfig()
    if (illustrated.value && imageSource.value === 'ai') payload.imageConfig = ai.getImageConfig()
    if (illustrated.value && imageSource.value === 'local' && images.value.length !== sceneCount.value) throw new Error('本地图片数量必须与分镜数量一致')
    submitting.value = true
    if (illustrated.value && imageSource.value === 'local') {
      for (const file of images.value) {
        const form = new FormData(); form.append('image', file)
        const response = await http.upload('/api/v2/animation/assets', form)
        payload.assetIds.push(response.data.id)
      }
    }
    const response = await http.post('/api/v2/animation/jobs', payload, { matrixSilentErrors: true })
    job.value = response.data
    sessionStorage.setItem(storageKey, job.value.id)
    if (mounted) await poll()
  } catch (err) { error.value = err.message }
  finally { submitting.value = false }
}
onMounted(() => { const id = sessionStorage.getItem(storageKey); if (id) { job.value = { id, status: 'queued', progress: 0, message: '正在恢复任务状态' }; poll() } })
onBeforeUnmount(() => { mounted = false; clearTimeout(timer) })
</script>

<style scoped>
.animation-grid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:20px;margin-top:16px}
.animation-surface,.status-card,.result-card{padding:28px;border:1px solid var(--border);border-radius:24px;background:var(--bg-elevated);box-shadow:var(--shadow-card)}
.animation-surface>header{display:flex;align-items:center;gap:14px;margin-bottom:24px}
.section-number{display:grid;place-items:center;width:36px;height:36px;border-radius:12px;background:var(--surface-active);color:var(--accent);font-weight:700}
h2{margin:0;font-size:20px}
h3{font-size:14px;margin:0 0 12px}
p{color:var(--text-muted);line-height:1.7;font-size:12px;margin:8px 0}
.field{display:flex;flex-direction:column;gap:10px;font-size:13px;font-weight:600;color:var(--text-primary)}
textarea,input[type=number],select{box-sizing:border-box;width:100%;border:1px solid var(--border);border-radius:12px;padding:12px 14px;font:inherit;font-weight:400;color:var(--text-primary);background:var(--bg-inset);outline-color:var(--accent)}
textarea{resize:vertical;line-height:1.8}
.parameters{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:24px}
fieldset{border:0;margin:0;padding:0;min-width:0}
fieldset:disabled{opacity:.65}
.image-section,.narration-section{padding:20px;margin-top:24px;border:1px solid var(--border);border-radius:16px;background:var(--bg-inset)}
.source-options{display:flex;gap:24px}
.source-options label,.narration-section label{font-size:13px;color:var(--text-primary)}
input[type=checkbox],input[type=radio]{accent-color:var(--accent)}
input[type=file]{max-width:100%;font-size:12px;margin-top:8px}
ol{padding-left:20px;color:var(--text-secondary);font-size:12px;line-height:1.8}
.service-note{display:flex;justify-content:space-between;gap:12px;margin-top:24px;font-size:12px;color:var(--text-secondary)}
.service-note a,.downloads a{color:var(--accent);text-decoration:none}
.privacy-note{font-size:11px}
.generate-button{margin-top:16px;height:46px;padding:0 30px;border:0;border-radius:12px;color:var(--accent-contrast);background:var(--accent-solid);font-weight:700;cursor:pointer}
.generate-button:disabled{opacity:.45;cursor:not-allowed}
.error{padding:14px;margin-top:16px;border-radius:12px;background:color-mix(in srgb, #e05a53 10%, var(--bg-elevated));color:var(--status-danger);font-size:13px;line-height:1.7}
.animation-rail{display:grid;align-content:start;gap:16px}
.eyebrow{display:block;color:var(--text-muted);font-size:10px;font-weight:700;letter-spacing:.14em;margin-bottom:10px}
.progress-number{text-align:center;font-size:46px;font-weight:700;color:var(--text-primary);margin:24px 0 16px}
.progress-number small{font-size:15px}
progress{width:100%;height:7px;accent-color:var(--accent)}
.status-card p{margin-top:16px}
.result-card video{display:block;width:100%;max-height:350px;background:#0c1222;border-radius:14px;margin:20px 0 16px}
.result-card strong{font-size:14px}
.downloads{display:flex;gap:18px;margin-top:14px;font-size:12px}
.empty-output{padding:35px 0;text-align:center}
.retry-button{border:0;background:var(--surface-active);color:var(--accent);padding:8px 12px;border-radius:8px;cursor:pointer}
@media(max-width:1100px){.animation-grid{grid-template-columns:1fr}
.animation-rail{grid-template-columns:1fr 1fr}
}
@media(max-width:720px){.parameters,.animation-rail{grid-template-columns:1fr}
.animation-surface{padding:20px}
.service-note{flex-direction:column}
}

</style>
