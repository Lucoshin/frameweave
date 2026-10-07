import test from 'node:test'
import assert from 'node:assert/strict'
import { validateAiConfig, publicAiSettings } from '../../../vendor/social-auto-upload-web-ui/frontend/src/utils/ai-settings.js'

test('AI 配置要求真实地址、密钥与模型，保留服务类型分离', () => {
  assert.throws(() => validateAiConfig({ baseUrl: '', apiKey: '', model: '' }, '图片'), /图片/)
  assert.throws(() => validateAiConfig({ baseUrl: 'file:///tmp', apiKey: 'secret', model: 'm' }, '文本'), /HTTP/)
  assert.deepEqual(validateAiConfig({ baseUrl: ' https://example.com/v1/ ', apiKey: ' key ', model: ' m ' }, '文本'), { baseUrl: 'https://example.com/v1', apiKey: 'key', model: 'm' })
})

test('持久化设置只包含公开配置，任何服务密钥均不落盘', () => {
  const result = publicAiSettings({ text: { baseUrl: 'https://text.test/v1', model: 't', apiKey: 'secret' }, image: { baseUrl: 'https://image.test/v1', model: 'i', apiKey: 'secret' }, speech: { provider: 'gpt_sovits', baseUrl: 'http://127.0.0.1:9880', apiKey: 'secret', refAudioPath: 'D:/voice.wav', promptText: '你好', promptLanguage: 'zh', textLanguage: 'zh', speed: 1 } })
  assert.equal(JSON.stringify(result).includes('secret'), false)
  assert.equal(result.image.model, 'i')
  assert.equal(result.speech.refAudioPath, 'D:/voice.wav')
})
