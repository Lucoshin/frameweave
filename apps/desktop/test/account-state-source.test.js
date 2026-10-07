import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const accountViewPath = path.resolve(
  'vendor/social-auto-upload-web-ui/frontend/src/views/AccountManagement.vue',
)
const desktopMainPath = path.resolve('apps/desktop/electron/main.js')
const desktopPreloadPath = path.resolve('apps/desktop/electron/preload.js')

test('账号页打开创作环境只使用 Python 平台引擎保存的 Cookie 登录态', async () => {
  const source = await readFile(accountViewPath, 'utf8')

  assert.match(source, /accountApi\.openCreatorCenter\(row\.id\)/)
  assert.doesNotMatch(source, /matrixDesktop\.openAccountWindow/)
  assert.doesNotMatch(source, /persist Session/)
})

test('账号页状态检测使用后端明确检查状态，未知结果不转成失效', async () => {
  const source = await readFile(accountViewPath, 'utf8')

  assert.match(source, /http\.get\('\/checkAccount', \{ id: row\.id \}, \{ matrixSilentErrors: true \}\)/)
  assert.match(source, /accountStore\.applyCheckStatus\(row\.id, status\)/)
  assert.doesNotMatch(source, /valid \? '正常' : '异常'/)
})

test('桌面壳不再暴露第二套 Electron 账号 Session', async () => {
  const [mainSource, preloadSource] = await Promise.all([
    readFile(desktopMainPath, 'utf8'),
    readFile(desktopPreloadPath, 'utf8'),
  ])

  for (const source of [mainSource, preloadSource]) {
    assert.doesNotMatch(source, /openAccountWindow/)
    assert.doesNotMatch(source, /accounts:open/)
    assert.doesNotMatch(source, /persist:matrix-account/)
  }
})
