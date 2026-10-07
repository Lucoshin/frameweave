export function validateServiceUrl(value, label) {
  let url
  try { url = new URL(String(value).trim()) } catch { throw new Error(`请在设置中填写${label}服务的 HTTP / HTTPS 地址`) }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error(`${label}服务必须使用不含凭证或查询参数的 HTTP / HTTPS 地址`)
  }
  return url.toString().replace(/\/$/, '')
}

export function validateAiConfig(config, label) {
  const baseUrl = validateServiceUrl(config.baseUrl, label)
  const apiKey = config.apiKey.trim()
  const model = config.model.trim()
  if (!apiKey || !model) throw new Error(`请在设置中填写${label}服务的 API Key 和模型`)
  return { baseUrl, apiKey, model }
}

export function validateSpeechConfig(config) {
  if (!['openai', 'gpt_sovits'].includes(config.provider)) throw new Error('不支持的语音服务类型')
  const result = { ...config, baseUrl: validateServiceUrl(config.baseUrl, '语音'), apiKey: config.apiKey.trim() }
  if (config.provider === 'openai') {
    if (!config.model.trim() || !config.voice.trim()) throw new Error('请在设置中填写语音模型和音色 ID')
  } else if (!config.refAudioPath.trim() || !config.promptText.trim()) {
    throw new Error('音色克隆需要参考音频路径和参考音频对应文本')
  }
  if (!Number.isFinite(config.speed) || config.speed < 0.5 || config.speed > 2) throw new Error('语速必须介于 0.5 与 2 之间')
  return result
}

export function publicAiSettings(settings) {
  const publicConfig = ({ baseUrl, model }) => ({ baseUrl, model })
  const { provider, baseUrl, model, voice, refAudioPath, promptText, promptLanguage, textLanguage, speed } = settings.speech
  return {
    text: publicConfig(settings.text), image: publicConfig(settings.image),
    speech: { provider, baseUrl, model, voice, refAudioPath, promptText, promptLanguage, textLanguage, speed },
  }
}
