<template>
  <div class="copy-page">
    <nav class="mode-switch" role="tablist" aria-label="文案生成方式">
      <button role="tab" :aria-selected="activeMode === 'ai'" :class="{ active: activeMode === 'ai' }" @click="activeMode = 'ai'">
        <el-icon><MagicStick /></el-icon>
        <span><strong>AI 批量成文</strong><small>标题直接生成 Word</small></span>
      </button>
      <button role="tab" :aria-selected="activeMode === 'template'" :class="{ active: activeMode === 'template' }" @click="activeMode = 'template'">
        <el-icon><Document /></el-icon>
        <span><strong>模板套打</strong><small>JSON 填充现有模板</small></span>
      </button>
    </nav>

    <div class="copy-grid">
      <section class="editor-card">
        <template v-if="activeMode === 'ai'">
          <div class="output-switch" role="group" aria-label="输出内容">
            <strong>输出内容</strong>
            <button :class="{ selected: outputMode === 'text' }" :aria-pressed="outputMode === 'text'" @click="outputMode = 'text'">纯文字</button>
            <button :class="{ selected: outputMode === 'illustrated' }" :aria-pressed="outputMode === 'illustrated'" @click="outputMode = 'illustrated'">图文</button>
          </div>
          <div class="section-head">
            <div><span class="step">01</span><div><h2>批量标题</h2><p>每行一个标题，空行自动忽略，重复标题分别生成。</p></div></div>
            <span class="count-tag">{{ titleCount }} 篇</span>
          </div>
          <textarea
            v-model="titlesText"
            class="titles-input"
            spellcheck="false"
            aria-label="批量文章标题"
            placeholder="例如：&#10;夏季门店引流的三个实用方法&#10;新账号如何规划第一周内容&#10;短视频标题常见的五个误区"
          ></textarea>

          <div class="section-head spaced-head">
            <div><span class="step">02</span><div><h2>写作要求</h2><p>说明受众、语气、篇幅与必须覆盖的信息。</p></div></div>
          </div>
          <textarea
            v-model="aiConfig.prompt"
            class="prompt-input"
            aria-label="AI 写作提示词"
            placeholder="例如：面向小微商家，语气自然克制，正文约 800 字，给出可执行步骤，不使用 Markdown。"
          ></textarea>

          <section v-if="outputMode === 'illustrated'" class="illustration-card">
            <div class="section-head"><div><span class="step"><Picture /></span><div><h2>文章配图</h2><p>图片嵌入 Word，原图同时保存到独立目录。</p></div></div></div>
            <div class="output-switch image-switch" role="group" aria-label="配图来源">
              <strong>配图来源</strong>
              <button :class="{ selected: imageSource === 'local' }" :aria-pressed="imageSource === 'local'" @click="imageSource = 'local'">本地图片</button>
              <button :class="{ selected: imageSource === 'ai' }" :aria-pressed="imageSource === 'ai'" @click="imageSource = 'ai'">AI 生成</button>
            </div>
            <template v-if="imageSource === 'local'">
              <label class="image-picker"><el-icon><Upload /></el-icon><strong>{{ readingImages ? '正在读取…' : '选择 1–4 张图片' }}</strong><small>PNG · JPEG · WebP，每张 ≤ 20 MB</small><input type="file" accept="image/png,image/jpeg,image/webp" multiple :disabled="readingImages || aiRunning" @change="chooseLocalImages" /></label>
              <p class="image-note">本批次每篇文章使用同一组图片，按正文段落分布插入。</p>
              <div v-if="localImages.length" class="image-thumbnails"><figure v-for="(image, index) in localImages" :key="image.name + index"><img :src="image.preview" :alt="image.name" /><figcaption>{{ image.name }}</figcaption><button type="button" :aria-label="`移除 ${image.name}`" @click="localImages.splice(index, 1)">×</button></figure></div>
            </template>
            <template v-else>
              <label class="field image-count"><span>每篇配图数量</span><select v-model.number="imageCount"><option v-for="count in 4" :key="count" :value="count">{{ count }} 张</option></select></label>
              <textarea v-model="imagePrompt" class="prompt-input image-prompt" aria-label="AI 配图要求" placeholder="例如：清新扁平插画，蓝绿色调，不要文字；图片与文章主题相符。"></textarea>
              <p class="image-note">按每篇标题与正文单独生成，共 {{ titleCount * imageCount }} 张。使用设置中的图片模型，生成费用由你的服务商计费。</p>
            </template>
          </section>

          <div class="section-head spaced-head">
            <div><span class="step">03</span><div><h2>AI 服务与保存位置</h2><p>使用设置中的公共 AI 配置；密钥仅保留在当前应用会话中。</p></div></div>
            <span class="memory-tag">不保存密钥</span>
          </div>
          <div class="config-grid">
            <router-link class="service-summary field-wide" to="/settings"><el-icon><Setting /></el-icon><span>文本模型：{{ aiStore.text.model || '尚未配置' }}<small v-if="outputMode === 'illustrated' && imageSource === 'ai'">图片模型：{{ aiStore.image.model || '尚未配置' }}</small></span><strong>前往设置 →</strong></router-link>
            <div class="field field-wide">
              <span>Word 保存目录</span>
              <div class="directory-control">
                <input v-model="aiConfig.outputDirectory" autocomplete="off" placeholder="例如 D:\文案输出" />
                <button type="button" @click="chooseAiOutputDirectory">选择目录</button>
              </div>
              <small>请输入当前电脑上的绝对路径；同名文件自动编号，不覆盖已有文件。</small>
            </div>
          </div>

          <div class="action-row">
            <label class="include-title">
              <input v-model="aiConfig.includeTitle" type="checkbox" />
              <span class="checkmark"></span>
              Word 正文顶部写入标题
            </label>
            <button class="generate" :disabled="!canGenerateAi" @click="generateAiBatch">
              <el-icon><MagicStick /></el-icon>
              {{ aiRunning ? '正在逐篇生成…' : outputMode === 'illustrated' ? `生成 ${titleCount || ''} 篇图文 Word` : `开始生成 ${titleCount || ''} 篇` }}
              <el-icon><ArrowRight /></el-icon>
            </button>
          </div>

          <div v-if="aiError" class="message error" role="alert"><strong>AI 生成失败</strong><span>{{ aiError }}</span></div>

          <section v-if="result" class="result-panel" aria-live="polite">
            <header>
              <div><span class="eyebrow">GENERATION RESULT</span><h3>本轮生成结果</h3></div>
              <div class="result-summary">
                <span class="success-dot"></span>{{ result.succeeded }} 成功
                <span class="failure-dot"></span>{{ result.failed }} 失败
              </div>
            </header>
            <div class="result-list">
              <article v-for="item in result.items" :key="`${item.order}-${item.title}`" :class="item.status">
                <span class="result-order">{{ String(item.order).padStart(2, '0') }}</span>
                <div>
                  <strong>{{ item.title }}</strong>
                  <small v-if="item.output_path">{{ item.output_path }}</small>
                  <small v-if="item.image_paths?.length">配图 {{ item.image_paths.length }} 张 · {{ item.image_paths[0].replace(/[\\/][^\\/]+$/, '') }}</small>
                  <small v-if="!item.output_path" class="result-error">{{ item.error || '生成失败' }}</small>
                </div>
                <span class="result-status">{{ item.status === 'succeeded' ? '已生成' : '失败' }}</span>
              </article>
            </div>
          </section>
        </template>

        <template v-else>
          <div class="section-head">
            <div><span class="step">01</span><div><h2>选择模板与输出目录</h2><p>模板字段使用 {title}、{content} 等占位符。</p></div></div>
            <span class="local-tag">仅本地处理</span>
          </div>
          <button class="template-picker" @click="chooseTemplate">
            <span class="file-icon"><el-icon><Document /></el-icon></span>
            <span><strong>{{ workflow ? fileName(workflow.templatePath) : '选择 .docx 模板' }}</strong><small>{{ workflow ? workflow.outputDirectory : '同时选择生成文件的保存目录' }}</small></span>
            <el-icon><ArrowRight /></el-icon>
          </button>
          <div class="section-head spaced-head">
            <div><span class="step">02</span><div><h2>粘贴批量 JSON 数据</h2><p>数组中的每个对象生成一个 Word 文件。</p></div></div>
          </div>
          <textarea v-model="jsonText" class="json-input" spellcheck="false" aria-label="批量 JSON 数据"></textarea>
          <div class="field-row"><label>文件名字段<input v-model="filenameField" /></label><span>默认读取每条数据的 title 字段</span></div>
          <div v-if="message" class="message" :class="messageType">{{ message }}</div>
          <button class="generate template-generate" :disabled="!workflow || running" @click="generateTemplateBatch">
            {{ running ? '正在生成…' : '批量生成 Word' }}<el-icon><ArrowRight /></el-icon>
          </button>
        </template>
      </section>

      <aside>
        <template v-if="activeMode === 'ai'">
          <section class="guide-card workflow-guide">
            <span class="eyebrow">HOW IT WORKS</span>
            <h3>一次配置，逐篇交付</h3>
            <ol>
              <li><span>1</span><div><strong>整理标题</strong><small>一行对应一个 Word</small></div></li>
              <li><span>2</span><div><strong>统一写作要求</strong><small>每篇自动带入对应标题</small></div></li>
              <li><span>3</span><div><strong>检查结果</strong><small>单篇失败不影响其他文章</small></div></li>
            </ol>
          </section>
          <section class="guide-card format-card">
            <span class="eyebrow">OUTPUT</span>
            <div class="word-sheet" :class="{ illustrated: outputMode === 'illustrated' }"><strong>文章标题</strong><div v-if="outputMode === 'illustrated'" class="sheet-picture"><el-icon><Picture /></el-icon><span>配图位置示意</span></div><i></i><i></i><i class="short"></i></div>
            <p>{{ outputMode === 'illustrated' ? '图文 Word + 独立 PNG 原图；图片真实嵌入，可离线查看。' : '直接生成标准 .docx，同名文件自动追加序号。' }}</p>
          </section>
        </template>
        <template v-else>
          <section class="guide-card"><span class="eyebrow">模板示例</span><pre>岗位名称：{title}
工作地点：{address}
薪资待遇：{salary}
岗位要求：{requirements}</pre></section>
          <section class="guide-card"><span class="eyebrow">JSON 示例</span><pre>[{
  "title": "深圳展会协助",
  "address": "会展中心",
  "salary": "220元/天"
}]</pre></section>
        </template>
        <section class="privacy-card">
          <el-icon><Lock /></el-icon>
          <div v-if="activeMode === 'ai'"><strong>密钥不落盘</strong><p>API Key 只保存在当前应用会话中。标题与提示词会发送到设置中的文本服务；AI 配图还会向图片服务发送正文与配图要求。</p></div>
          <div v-else><strong>模板数据不上传</strong><p>模板和 JSON 只在当前电脑读取与写入。</p></div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ArrowRight, Document, Lock, MagicStick, Picture, Setting, Upload } from '@element-plus/icons-vue'
import { wordApi } from '@/api/word'
import { useAiStore } from '@/stores/ai'
import { buildWordGenerationPayload, parseTitleLines } from '@/utils/word-generation'

const activeMode = ref('ai')
const aiStore = useAiStore()
const outputMode = ref('text')
const imageSource = ref('local')
const imageCount = ref(1)
const imagePrompt = ref('')
const localImages = ref([])
const readingImages = ref(false)
const titlesText = ref('')
const aiRunning = ref(false)
const aiError = ref('')
const result = ref(null)
const aiConfig = reactive({
  prompt: '',
  outputDirectory: '',
  includeTitle: true,
})

const titleCount = computed(() => parseTitleLines(titlesText.value).length)
const canGenerateAi = computed(() => (
  titleCount.value > 0
  && aiConfig.prompt.trim()
  && aiConfig.outputDirectory.trim()
  && !aiRunning.value
  && !readingImages.value
))

async function chooseLocalImages(event) {
  const files = Array.from(event.target.files)
  event.target.value = ''
  if (!files.length) return
  aiError.value = ''
  if (files.length > 4 || files.some(file => file.size > 20 * 1024 * 1024 || !['image/png', 'image/jpeg', 'image/webp'].includes(file.type))) {
    aiError.value = '请选择 1–4 张 PNG、JPEG 或 WebP 图片，每张不超过 20 MB'
    return
  }
  readingImages.value = true
  try {
    localImages.value = await Promise.all(files.map(file => new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve({ name: file.name, data: String(reader.result).split(',')[1], preview: reader.result })
      reader.onerror = () => reject(new Error(`无法读取图片：${file.name}`))
      reader.readAsDataURL(file)
    })))
  } catch (error) {
    aiError.value = error.message
  } finally {
    readingImages.value = false
  }
}

async function chooseAiOutputDirectory() {
  if (!window.matrixDesktop) {
    aiError.value = '请在映织桌面端中选择 Word 保存目录'
    return
  }
  aiConfig.outputDirectory = await window.matrixDesktop.chooseOutputDirectory()
    || aiConfig.outputDirectory
}

async function generateAiBatch() {
  aiRunning.value = true
  aiError.value = ''
  result.value = null
  try {
    const textConfig = aiStore.getTextConfig()
    let images
    if (outputMode.value === 'illustrated') {
      if (imageSource.value === 'local') {
        if (!localImages.value.length) throw new Error('请选择本地配图')
        images = { mode: 'local', files: localImages.value.map(({ name, data }) => ({ name, data })) }
      } else {
        if (!imagePrompt.value.trim()) throw new Error('请填写 AI 配图要求')
        images = { mode: 'ai', count: imageCount.value, prompt: imagePrompt.value.trim(), provider: aiStore.getImageConfig() }
      }
    }
    const response = await wordApi.generate(buildWordGenerationPayload({
      titlesText: titlesText.value,
      ...aiConfig,
      ...textConfig,
      images,
    }))
    result.value = response.data
  } catch (error) {
    aiError.value = error.message || 'AI 生成失败，请检查接口配置后重试'
  } finally {
    aiRunning.value = false
  }
}

const workflow = ref(null)
const jsonText = ref('[\n  {\n    "title": "第一篇文案",\n    "content": "在这里填写正文"\n  }\n]')
const filenameField = ref('title')
const running = ref(false)
const message = ref('')
const messageType = ref('')
const fileName = path => path?.split(/[\\/]/).pop()

async function chooseTemplate() {
  if (!window.matrixDesktop) {
    message.value = '请在 Electron 桌面端中选择模板。'
    messageType.value = 'info'
    return
  }
  workflow.value = await window.matrixDesktop.chooseWordWorkflow() || workflow.value
}

async function generateTemplateBatch() {
  running.value = true
  message.value = ''
  try {
    const templateResult = await window.matrixDesktop.generateWordBatch({
      ...workflow.value,
      jsonText: jsonText.value,
      filenameField: filenameField.value,
    })
    message.value = `已生成 ${templateResult.count} 个 Word 文件，保存到 ${workflow.value.outputDirectory}`
    messageType.value = 'success'
  } catch (error) {
    message.value = error.message || '生成失败'
    messageType.value = 'error'
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.output-switch{display:flex;align-items:center;gap:8px;margin-bottom:22px}
.output-switch>strong{font-size:12px;margin-right:8px}
.output-switch button{padding:8px 17px;border:1px solid var(--border);border-radius:9px;background:var(--bg-elevated);color:var(--text-secondary);cursor:pointer;font-size:12px}
.output-switch button.selected{border-color:var(--accent);color:var(--accent);background:var(--surface-active)}
.illustration-card{padding:18px;margin-top:20px;border:1px solid var(--border);border-radius:15px;background:var(--bg-inset)}
.image-switch{margin-top:17px;margin-bottom:12px}
.image-picker{display:flex;min-height:95px;align-items:center;justify-content:center;flex-direction:column;gap:5px;border:1px dashed var(--border);border-radius:12px;background:var(--bg-elevated);color:var(--accent);cursor:pointer}
.image-picker>.el-icon{font-size:22px}
.image-picker strong{font-size:12px}
.image-picker small,.image-note{font-size:10px;color:var(--text-muted);line-height:1.7}
.image-picker input{width:1px;height:1px;opacity:0;position:absolute}
.image-picker:focus-within{outline:2px solid var(--accent)}
.image-note{margin:8px 0 0}
.image-thumbnails{display:flex;gap:10px;margin-top:12px;flex-wrap:wrap}
.image-thumbnails figure{position:relative;width:90px;margin:0}
.image-thumbnails img{width:90px;height:66px;object-fit:cover;border-radius:8px}
.image-thumbnails figcaption{font-size:9px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;color:var(--text-secondary)}
.image-thumbnails button{position:absolute;right:-5px;top:-5px;border:0;border-radius:50%;width:20px;height:20px;color:var(--accent-contrast);background:#63718a;cursor:pointer}
.image-count{max-width:180px}
.image-prompt{height:85px}
.service-summary{display:flex;gap:9px;align-items:center;color:var(--text-secondary);text-decoration:none;font-size:11px;padding:10px;border-radius:10px;background:var(--surface-active)}
.service-summary small{display:block;margin-top:4px;color:var(--text-muted)}
.service-summary strong{margin-left:auto;font-size:10px;white-space:nowrap;color:var(--accent)}
.word-sheet.illustrated{height:170px}
.sheet-picture{height:62px;margin-top:10px;border-radius:5px;background:var(--surface-active);display:flex;align-items:center;justify-content:center;gap:6px;color:var(--text-muted);font-size:8px}
.sheet-picture .el-icon{font-size:23px}

.copy-page{max-width:1180px;margin:auto;color:var(--text-primary)}
.eyebrow{color:var(--text-muted);font-size:9px;font-weight:750;letter-spacing:.14em}
.mode-switch{width:min(540px,100%);margin-top:0;padding:4px;display:grid;grid-template-columns:1fr 1fr;gap:4px;border:1px solid var(--border);border-radius:16px;background:var(--bg-inset)}
.mode-switch button{min-height:54px;padding:8px 14px;display:flex;align-items:center;gap:10px;text-align:left;border:0;border-radius:12px;color:var(--text-secondary);background:transparent;cursor:pointer;transition:.18s ease}
.mode-switch button>.el-icon{font-size:17px}
.mode-switch button strong,.mode-switch button small{display:block}
.mode-switch button strong{font-size:12px}
.mode-switch button small{margin-top:2px;color:var(--text-muted);font-size:9px}
.mode-switch button.active{color:var(--accent);background:var(--bg-elevated);box-shadow:var(--shadow-card)}
.copy-grid{margin-top:15px;display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:16px}
.editor-card,.guide-card,.privacy-card{border:1px solid var(--border);background:var(--bg-elevated);box-shadow:0 12px 34px var(--border)}
.editor-card{padding:24px;border-radius:21px}
.section-head{display:flex;align-items:center;justify-content:space-between}
.section-head>div{display:flex;align-items:flex-start;gap:10px}
.section-head h2{margin:1px 0 0;font-size:15px}
.section-head p{margin:4px 0 0;color:var(--text-muted);font-size:9px}
.step{width:25px;height:25px;display:grid;place-items:center;flex:0 0 auto;border-radius:8px;color:var(--accent);background:var(--surface-active);font-size:9px;font-weight:750}
.count-tag,.memory-tag,.local-tag{padding:5px 9px;border-radius:20px;font-size:9px;font-weight:700}
.count-tag{color:var(--accent);background:var(--surface-active)}
.memory-tag,.local-tag{color:var(--status-success);background:color-mix(in srgb, #2fb778 10%, var(--bg-elevated))}
.spaced-head{margin-top:23px}
.titles-input,.prompt-input,.json-input{width:100%;margin-top:14px;padding:14px 15px;box-sizing:border-box;resize:vertical;border:1px solid var(--border);border-radius:14px;outline:0;color:var(--text-primary);background:var(--bg-inset);font:12px/1.7 "SFMono-Regular",Consolas,monospace;transition:.18s ease}
.titles-input{height:150px}
.prompt-input{height:112px;font-family:"Microsoft YaHei UI","PingFang SC",sans-serif}
.json-input{height:260px}
.titles-input:focus,.prompt-input:focus,.json-input:focus,.field input:focus,.field select:focus,.field-row input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(23,108,245,.08)}
.config-grid{margin-top:15px;padding:16px;display:grid;grid-template-columns:1fr 1fr;gap:13px;border:1px solid var(--border);border-radius:16px;background:var(--bg-inset)}
.field{display:grid;gap:6px;color:var(--text-secondary);font-size:9px;font-weight:650}
.field-wide{grid-column:1/-1}
.field input,.field select{width:100%;height:36px;padding:0 11px;box-sizing:border-box;border:1px solid var(--border);border-radius:10px;outline:0;color:var(--text-primary);background:var(--bg-elevated);font-size:11px}
.field small{color:var(--text-muted);font-size:9px;font-weight:400}
.action-row{margin-top:17px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.include-title{display:flex;align-items:center;gap:8px;color:var(--text-secondary);font-size:10px;cursor:pointer}
.include-title input{position:absolute;opacity:0;pointer-events:none}
.checkmark{width:16px;height:16px;display:grid;place-items:center;border:1px solid var(--border);border-radius:5px;background:var(--bg-elevated)}
.include-title input:checked+.checkmark{border-color:var(--accent);background:var(--accent-solid)}
.include-title input:checked+.checkmark:after{content:"";width:7px;height:4px;border-left:2px solid var(--accent-contrast);border-bottom:2px solid var(--accent-contrast);transform:rotate(-45deg) translate(1px,-1px)}
.generate{height:40px;padding:0 16px;display:flex;align-items:center;justify-content:center;gap:7px;border:0;border-radius:12px;color:var(--accent-contrast);background:var(--accent-solid);box-shadow:0 8px 18px rgba(23,108,245,.18);font-size:11px;font-weight:700;cursor:pointer;transition:.18s ease}
.generate:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 11px 23px rgba(23,108,245,.24)}
.generate:disabled{opacity:.38;box-shadow:none;cursor:not-allowed}
.message{margin-top:14px;padding:11px 13px;display:flex;gap:8px;border-radius:11px;font-size:10px}
.message strong{white-space:nowrap}
.message.success{color:var(--status-success);background:color-mix(in srgb, #2fb778 10%, var(--bg-elevated))}
.message.error{color:var(--status-danger);background:color-mix(in srgb, #e05a53 10%, var(--bg-elevated))}
.message.info{color:var(--accent);background:var(--surface-active)}
.result-panel{margin-top:18px;padding:17px;border:1px solid var(--border);border-radius:16px;background:var(--bg-inset)}
.result-panel>header{display:flex;align-items:center;justify-content:space-between}
.result-panel h3{margin:4px 0 0;font-size:14px}
.result-summary{display:flex;align-items:center;gap:6px;color:var(--text-secondary);font-size:9px}
.success-dot,.failure-dot{width:6px;height:6px;margin-left:5px;border-radius:50%}
.success-dot{background:#34b875}
.failure-dot{background:#e06b64}
.result-list{margin-top:13px;display:grid;gap:7px}
.result-list article{min-height:50px;padding:9px 11px;display:grid;grid-template-columns:28px minmax(0,1fr) auto;align-items:center;gap:10px;border:1px solid var(--border);border-radius:11px;background:var(--bg-elevated)}
.result-list article.failed{border-color:rgba(208,85,78,.16);background:color-mix(in srgb, #e05a53 5%, var(--bg-elevated))}
.result-order{color:var(--text-muted);font:9px "SFMono-Regular",Consolas,monospace}
.result-list strong,.result-list small{display:block}
.result-list strong{overflow:hidden;font-size:10px;text-overflow:ellipsis;white-space:nowrap}
.result-list small{margin-top:3px;overflow:hidden;color:var(--text-muted);font-size:8px;text-overflow:ellipsis;white-space:nowrap}
.result-list .result-error{color:var(--status-danger)}
.result-status{padding:4px 7px;border-radius:20px;color:var(--status-success);background:color-mix(in srgb, #2fb778 10%, var(--bg-elevated));font-size:8px;font-weight:700}
.failed .result-status{color:var(--status-danger);background:color-mix(in srgb, #e05a53 10%, var(--bg-elevated))}
.template-picker{width:100%;min-height:76px;margin-top:15px;padding:13px;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:12px;text-align:left;border:1px solid var(--border);border-radius:15px;color:var(--text-primary);background:var(--bg-inset);cursor:pointer}
.file-icon{width:42px;height:42px;display:grid;place-items:center;border-radius:12px;color:var(--accent);background:var(--surface-active)}
.template-picker strong,.template-picker small{display:block}
.template-picker strong{font-size:12px}
.template-picker small{max-width:520px;margin-top:4px;overflow:hidden;color:var(--text-muted);font-size:9px;text-overflow:ellipsis;white-space:nowrap}
.field-row{margin-top:12px;display:flex;align-items:flex-end;justify-content:space-between}
.field-row label{display:grid;gap:5px;color:var(--text-secondary);font-size:9px}
.field-row input{color:var(--text-primary);background:var(--bg-elevated);width:150px;height:32px;padding:0 10px;box-sizing:border-box;border:1px solid var(--border);border-radius:9px;outline:0}
.field-row>span{color:var(--text-muted);font-size:9px}
.template-generate{width:100%;margin-top:16px}
aside{display:grid;align-content:start;gap:12px}
.guide-card{padding:18px;border-radius:17px}
.guide-card h3{margin:7px 0 0;font-size:14px}
.guide-card pre{margin:13px 0 0;padding:13px;overflow:auto;border-radius:11px;color:var(--text-secondary);background:var(--bg-inset);font:10px/1.7 "SFMono-Regular",Consolas,monospace}
.workflow-guide ol{margin:16px 0 0;padding:0;display:grid;gap:14px;list-style:none}
.workflow-guide li{display:flex;align-items:center;gap:10px}
.workflow-guide li>span{width:24px;height:24px;display:grid;place-items:center;flex:0 0 auto;border-radius:8px;color:var(--accent);background:var(--surface-active);font-size:9px;font-weight:750}
.workflow-guide strong,.workflow-guide small{display:block}
.workflow-guide strong{font-size:10px}
.workflow-guide small{margin-top:2px;color:var(--text-muted);font-size:8px}
.word-sheet{height:108px;margin-top:13px;padding:18px;box-sizing:border-box;border:1px solid var(--border);border-radius:7px;background:var(--bg-elevated);box-shadow:0 8px 20px var(--border);transform:rotate(1deg)}
.word-sheet strong{display:block;text-align:center;font-size:10px}
.word-sheet i{height:3px;margin-top:12px;display:block;border-radius:2px;background:var(--border)}
.word-sheet i.short{width:62%}
.format-card p{margin:13px 0 0;color:var(--text-muted);font-size:9px;line-height:1.55}
.privacy-card{padding:16px;display:flex;gap:11px;border-radius:17px;color:var(--status-success)}
.privacy-card>.el-icon{margin-top:2px;flex:0 0 auto}
.privacy-card strong{font-size:11px}
.privacy-card p{margin:3px 0 0;color:var(--text-muted);font-size:9px;line-height:1.55}
@media(max-width:900px){.copy-grid{grid-template-columns:1fr}
}
@media(max-width:640px){.mode-switch{grid-template-columns:1fr}
.config-grid{grid-template-columns:1fr}
.field-wide{grid-column:auto}
.action-row{align-items:stretch;flex-direction:column}
.generate{width:100%}
.editor-card{padding:18px}
.section-head{gap:10px;align-items:flex-start}
}

.directory-control{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px}
.directory-control button{height:36px;padding:0 12px;border:0;border-radius:10px;color:var(--accent);background:var(--surface-active);font-size:9px;font-weight:700;cursor:pointer}

</style>
