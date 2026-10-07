import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

test('AI 服务的 HTTP 502/503/504 错误保留后端原因，并遵守静默错误配置', async () => {
  const source = readFileSync('vendor/social-auto-upload-web-ui/frontend/src/utils/request.js', 'utf8')
    .replace(/^import .+$/gm, '')
    .replace(/import\.meta\.env\.VITE_API_BASE_URL/g, "''")
    .replace('export const http', 'const http')
    .replace('export default request', '')
  let onResponseError
  const messages = []
  vm.runInNewContext(source, {
    axios: { create: () => ({ interceptors: {
      request: { use() {} },
      response: { use(_success, failure) { onResponseError = failure } },
    } }) },
    ElMessage: { error: message => messages.push(message) },
    console: { error() {} },
  })

  for (const status of [502, 503, 504]) {
    const message = `语音服务返回 HTTP ${status}，请检查配置`
    const error = { response: { status, data: { msg: message } } }
    await assert.rejects(onResponseError(error), rejected => rejected === error && rejected.message === message)
    assert.equal(messages.at(-1), message)
  }
  const silent = { config: { matrixSilentErrors: true }, response: { status: 502, data: { msg: '音色服务暂不可用' } } }
  await assert.rejects(onResponseError(silent), error => error.message === '音色服务暂不可用')
  assert.equal(messages.length, 3)
})
