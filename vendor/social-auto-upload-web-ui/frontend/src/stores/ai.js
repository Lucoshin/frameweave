import { defineStore } from 'pinia'
import { reactive } from 'vue'
import { publicAiSettings, validateAiConfig, validateSpeechConfig } from '../utils/ai-settings.js'

const STORAGE_KEY = 'matrix_ai_services_v1'

export const useAiStore = defineStore('ai', () => {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  const text = reactive({ baseUrl: '', model: '', ...saved.text, apiKey: '' })
  const image = reactive({ baseUrl: '', model: '', ...saved.image, apiKey: '' })
  const speech = reactive({ provider: 'openai', baseUrl: '', model: '', voice: '', refAudioPath: '', promptText: '', promptLanguage: 'zh', textLanguage: 'zh', speed: 1, ...saved.speech, apiKey: '' })

  // 密钥仅保存在共享页面会话中；持久化必须使用白名单，不能直接序列化 store。
  function saveSettings() { localStorage.setItem(STORAGE_KEY, JSON.stringify(publicAiSettings({ text, image, speech }))) }
  function clearKeys() { text.apiKey = ''; image.apiKey = ''; speech.apiKey = '' }
  return { text, image, speech, saveSettings, clearKeys,
    getTextConfig: () => validateAiConfig(text, '文本'),
    getImageConfig: () => validateAiConfig(image, '图片'),
    getSpeechConfig: () => validateSpeechConfig(speech),
  }
})
