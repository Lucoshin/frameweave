import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'

const frontendDir = path.resolve('vendor/social-auto-upload-web-ui/frontend')
const loginDialogPath = path.join(frontendDir, 'src', 'components', 'LoginDialog.vue')
const accountApiPath = path.join(frontendDir, 'src', 'api', 'account.js')

async function readLoginSources() {
  return Promise.all([
    readFile(loginDialogPath, 'utf8'),
    readFile(accountApiPath, 'utf8'),
  ])
}

test('登录取消 API 使用当前 UUID 会话调用后端取消端点', async () => {
  const [dialogSource, accountApiSource] = await readLoginSources()

  assert.match(accountApiSource, /cancelLoginSession\s*\(sessionId\)/)
  assert.match(
    accountApiSource,
    /http\.post\(\s*`\/api\/login-sessions\/\$\{encodeURIComponent\(sessionId\)\}\/cancel`/,
  )
  assert.match(dialogSource, /const sessionId = crypto\.randomUUID\(\)/)
  assert.match(
    dialogSource,
    /loginSessions\.set\(platformKey,\s*\{\s*sessionId,\s*eventSource\s*\}\s*\)/s,
  )
})

test('添加账号弹窗只允许一个平台登录并明确提示其他卡片等待', async () => {
  const [dialogSource] = await readLoginSources()

  assert.match(dialogSource, /const activeLoginKey = ref\(/)
  assert.match(
    dialogSource,
    /activeLoginKey\.value\s*&&\s*activeLoginKey\.value\s*!==\s*platformKey/,
  )
  assert.match(dialogSource, /activeLoginKey\.value\s*=\s*platformKey/)
  assert.match(dialogSource, /请先完成当前登录/)
  assert.match(dialogSource, /:aria-disabled="p\.isBlocked"/)
})

test('SSE 使用新 progress success error 契约并仅保留指定旧状态过渡', async () => {
  const [dialogSource] = await readLoginSources()

  for (const status of ['progress', 'success', 'error', '200', '500', '0', 'failed']) {
    assert.match(dialogSource, new RegExp(`['"]${status}['"]`), `缺少 ${status} 状态处理`)
  }
  assert.match(dialogSource, /浏览器可能在主窗口后方，请在任务栏切换/)
  assert.match(dialogSource, /result\.msg\s*\|\|\s*LOGIN_PROGRESS_HINT/)
  assert.match(dialogSource, /result\.msg/)
  assert.doesNotMatch(dialogSource, /result\.error/)
})

test('成功和失败都会释放全局登录互斥且添加模式显示真实错误', async () => {
  const [dialogSource] = await readLoginSources()

  const successBranch = dialogSource.match(/if \(status === 'success'[\s\S]*?return\s*\n\s*\}/)?.[0] || ''
  const errorBranch = dialogSource.match(/if \(errorStatuses\.has\(status\)\)[\s\S]*?return\s*\n\s*\}/)?.[0] || ''

  assert.match(successBranch, /releaseLogin\(platformKey\)/)
  assert.match(errorBranch, /releaseLogin\(platformKey\)/)
  assert.match(dialogSource, /\{\{\s*p\.message\s*\|\|\s*'登录失败'\s*\}\}/)
  assert.match(dialogSource, /result\.data\?\.detail\s*\|\|\s*''/)
  assert.match(dialogSource, /showErrorDetail\(p\.detail\)/)
  assert.match(dialogSource, /class="status-message"/)
  assert.match(dialogSource, /-webkit-line-clamp:\s*2/)
})

test('取消和关闭弹窗均先等待后端取消再关闭本地 SSE', async () => {
  const [dialogSource] = await readLoginSources()

  const cancelStart = dialogSource.indexOf('async function cancelLoginSession(platformKey)')
  const cancelEnd = dialogSource.indexOf('function onCardClick', cancelStart)
  const cancelFunction = dialogSource.slice(cancelStart, cancelEnd)
  const cancelRequestIndex = cancelFunction.indexOf(
    'await accountApi.cancelLoginSession(session.sessionId)',
  )
  const closeIndex = cancelFunction.lastIndexOf('releaseLogin(platformKey)')

  assert.ok(cancelRequestIndex >= 0, '取消流程必须请求后端 cancel')
  assert.ok(closeIndex > cancelRequestIndex, '必须在后端 cancel 请求完成后关闭 SSE')
  assert.match(dialogSource, /async function handleClose\(\)/)
  assert.match(dialogSource, /await cancelLoginSession\(platformKey\)/)
  assert.match(dialogSource, /async function cancelLogin\(platformKey\)/)
  assert.match(dialogSource, /async function cancelRelogin\(\)/)
})
