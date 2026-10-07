<template>
  <section class="ai-services">
    <div class="ai-heading"><div><h2>AI 服务</h2><p>文案、配图、动画与配音共用这里的配置。</p></div><span class="session-badge">密钥仅本次会话有效</span></div>
    <div class="service-grid">
      <article v-for="service in services" :key="service.key" class="service-card">
        <h3>{{ service.title }}</h3><p>{{ service.description }}</p>
        <label>接口基础地址<input v-model="aiStore[service.key].baseUrl" :placeholder="service.placeholder" type="url" autocomplete="off"></label>
        <label>模型名称<input v-model="aiStore[service.key].model" placeholder="填写服务商提供的模型 ID" autocomplete="off"></label>
        <label>API Key（接口密钥）<input v-model="aiStore[service.key].apiKey" type="password" placeholder="切换页面可复用，刷新后需重新输入" autocomplete="new-password"></label>
      </article>
    </div>
    <article class="service-card speech-card">
      <h3>配音与音色克隆</h3><p>动画可选择使用这里的语音服务。角色音色由服务端音色 ID 或参考音频决定。</p>
      <div class="service-grid">
        <label>接口类型<select v-model="aiStore.speech.provider"><option value="openai">通用 TTS（兼容 OpenAI 语音接口）</option><option value="gpt_sovits">GPT-SoVITS v2（参考音频克隆）</option></select></label>
        <label>接口基础地址<input v-model="aiStore.speech.baseUrl" :placeholder="aiStore.speech.provider === 'gpt_sovits' ? 'http://127.0.0.1:9880' : 'https://服务商域名/v1'" type="url"></label>
        <template v-if="aiStore.speech.provider === 'openai'">
          <label>语音模型<input v-model="aiStore.speech.model" placeholder="服务端支持的 TTS 模型 ID"></label>
          <label>音色 ID<input v-model="aiStore.speech.voice" placeholder="服务端提供的角色或音色 ID"></label>
        </template>
        <template v-else>
          <label class="full-width">参考音频路径<input v-model="aiStore.speech.refAudioPath" placeholder="GPT-SoVITS 服务所在电脑可读取的音频绝对路径"><small>远程服务需填写远程路径；使用本机服务时填写本机路径。</small></label>
          <label class="full-width">参考音频对应文本<textarea v-model="aiStore.speech.promptText" rows="2" placeholder="准确填写参考音频中说出的内容"></textarea></label>
          <label>参考音频语言<select v-model="aiStore.speech.promptLanguage"><option value="zh">中文</option><option value="en">英语</option><option value="ja">日语</option><option value="ko">韩语</option><option value="yue">粤语</option></select></label>
          <label>生成语音语言<select v-model="aiStore.speech.textLanguage"><option value="zh">中文</option><option value="en">英语</option><option value="ja">日语</option><option value="ko">韩语</option><option value="yue">粤语</option></select></label>
        </template>
        <label>语音接口密钥<input v-model="aiStore.speech.apiKey" type="password" autocomplete="new-password" placeholder="本地无认证服务可留空"></label>
        <label>语速<input v-model.number="aiStore.speech.speed" type="number" min="0.5" max="2" step="0.1"></label>
      </div>
      <p v-if="aiStore.speech.provider === 'gpt_sovits'" class="service-note">需先启动 GPT-SoVITS 的 api_v2.py 服务并加载音色模型。本应用连接该服务，不内置模型权重或角色音色库。</p>
      <div class="speech-preview"><label>试听文本<input v-model="previewText" placeholder="输入一段文字试听"></label><el-button :loading="previewing" :disabled="!previewText.trim()" @click="previewSpeech">生成试听</el-button></div>
      <p v-if="previewError" class="service-error" role="alert">{{ previewError }}</p>
      <audio v-if="previewUrl" :src="previewUrl" controls aria-label="合成语音试听"></audio>
    </article>
    <div class="ai-actions"><p>地址和模型会保存在本机。API Key 仅保留在当前页面会话；生成内容会发送到所配置的服务。</p><el-button @click="aiStore.clearKeys()">清除会话密钥</el-button><el-button type="primary" @click="save">保存 AI 设置</el-button></div>
  </section>
</template>

<script setup>
import { ref, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useAiStore } from '@/stores/ai'
import { http } from '@/utils/request'

const aiStore = useAiStore()
const services = [
  { key: 'text', title: '文本与分镜', description: '用于批量成文、动画创意与分镜。兼容 Chat Completions 接口。', placeholder: 'https://服务商域名/v1' },
  { key: 'image', title: '图片生成', description: '用于图文配图和图文动画。需支持 Images Generations 接口。', placeholder: 'https://图片服务商域名/v1' },
]
const previewText = ref('欢迎使用映织，这是我的配音试听。')
const previewing = ref(false)
const previewUrl = ref('')
const previewError = ref('')
function save() { aiStore.saveSettings(); ElMessage.success('AI 设置已保存，密钥仅在当前会话保留') }
async function previewSpeech() {
  previewError.value = ''
  previewUrl.value = ''
  previewing.value = true
  try {
    const response = await http.post('/api/v2/speech/preview', { text: previewText.value, config: aiStore.getSpeechConfig() }, { timeout: 240000 })
    if (response.code !== 200 || !response.data?.audioUrl) throw new Error(response.msg || '配音服务未返回音频')
    previewUrl.value = new URL(response.data.audioUrl, import.meta.env.VITE_API_BASE_URL || window.location.origin).href
  } catch (error) { previewError.value = error.message }
  finally { previewing.value = false }
}
onBeforeUnmount(() => { previewUrl.value = '' })
</script>

<style scoped>
.ai-services{margin:24px 0;padding:28px;border:1px solid var(--border);border-radius:20px;background:var(--bg-elevated);color:var(--text-primary)}
.ai-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.ai-heading h2{margin:0;font-size:22px}
.ai-services p{font-size:13px;line-height:1.7;color:var(--text-secondary);margin:8px 0 18px}
.session-badge{padding:7px 12px;border-radius:20px;background:color-mix(in srgb, #2fb778 10%, var(--bg-elevated));color:var(--status-success);font-size:12px;white-space:nowrap}
.service-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
.service-card{padding:22px;background:var(--bg-inset);border:1px solid var(--border);border-radius:16px}
.service-card h3{margin:0;font-size:16px}
.service-card label{display:flex;flex-direction:column;gap:8px;color:var(--text-secondary);font-size:13px;margin:14px 0}
.service-card input,.service-card select,.service-card textarea{box-sizing:border-box;width:100%;min-height:42px;padding:10px 12px;border:1px solid var(--border);border-radius:9px;background:var(--bg-elevated);color:var(--text-primary);font:inherit}
.service-card input:focus,.service-card select:focus,.service-card textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
.speech-card{margin-top:20px}
.full-width{grid-column:1/-1}
.service-card small{font-size:12px;color:var(--text-secondary)}
.speech-preview{display:flex;align-items:flex-end;gap:16px}
.speech-preview label{flex:1;margin-bottom:0}
.speech-preview .el-button{height:42px}
.service-error{color:var(--status-danger)!important}
.speech-card audio{width:100%;margin-top:16px}
.ai-actions{display:flex;align-items:center;gap:12px;margin-top:20px}
.ai-actions p{margin:0;flex:1}
@media(max-width:950px){.service-grid{grid-template-columns:1fr}
.ai-heading,.ai-actions{flex-wrap:wrap}
.full-width{grid-column:auto}
.ai-actions p{flex-basis:100%}
}

</style>
