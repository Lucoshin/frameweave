import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import { accountStatusAfterCheck } from '../../../vendor/social-auto-upload-web-ui/frontend/src/utils/accountCheck.js'

const sourceRoot = 'vendor/social-auto-upload-web-ui/frontend/src/'

function section(file, start, end) {
  const source = readFileSync(sourceRoot + file, 'utf8')
  const from = source.indexOf(start)
  const to = source.indexOf(end, from)
  assert.ok(from >= 0 && to > from, `未找到 ${file} 检查代码`)
  return source.slice(from, to)
}

test('只有已确认结果会更新账号状态，未知和未声明的枚举不会写成失效', () => {
  for (const previous of ['正常', '异常', '验证中']) {
    assert.equal(accountStatusAfterCheck(previous, 'unknown'), previous)
  }
  assert.equal(accountStatusAfterCheck('异常', 'valid'), '正常')
  assert.equal(accountStatusAfterCheck('正常', 'invalid'), '异常')
  assert.throws(() => accountStatusAfterCheck('正常', undefined), /未知的账号检查状态/)
  assert.throws(() => accountStatusAfterCheck('正常', false), /未知的账号检查状态/)
})

test('批量账号检查保留 unknown、网络中断和账号占用原因且不污染账号状态', async () => {
  const source = section('components/AccountCheckDialog.vue', 'async function checkCard(card)', 'async function retryCheck(card)')
  let response
  let storedStatus = '正常'
  const context = {
    http: { get: async () => {
      if (response instanceof Error) throw response
      return response
    } },
    accountStore: { applyCheckStatus(_id, status) {
      storedStatus = accountStatusAfterCheck(storedStatus, status)
    } },
  }
  vm.runInNewContext(`${source}\nglobalThis.run = checkCard`, context)
  for (const problem of [
    { data: { status: 'unknown', message: '未确认登录状态' } },
    new Error('网络连接失败'),
    new Error('该账号正在发布，请先完成或关闭当前账号窗口'),
    { data: { valid: false } },
  ]) {
    response = problem
    const card = { id: 1 }
    await context.run(card)
    assert.equal(card.resultStatus, 'unknown')
    assert.equal(card.checkStatus, 'checked')
    assert.equal(storedStatus, '正常')
    assert.ok(card.message)
  }
  response = { data: { status: 'invalid', message: '登录文件不存在' } }
  const missing = { id: 1 }
  await context.run(missing)
  assert.equal(missing.resultStatus, 'invalid')
  assert.equal(storedStatus, '异常')
  response = { data: { status: 'valid', message: '账号状态正常' } }
  await context.run(missing)
  assert.equal(storedStatus, '正常')
})

test('单账号检查不会将未知或失败覆盖成失效，并在请求结束后解锁检查按钮', async () => {
  const source = section('views/AccountManagement.vue', 'const handleCheckAccount = async (row)', 'const handleAddAccount =')
  let response
  let storedStatus = '正常'
  const notices = []
  const message = value => notices.push(value)
  message.warning = value => notices.push({ type: 'warning', message: value })
  message.error = value => notices.push({ type: 'error', message: value })
  const context = {
    checkingIds: { value: new Set() },
    http: { get: async () => {
      if (response instanceof Error) throw response
      return response
    } },
    accountStore: { applyCheckStatus(_id, status) {
      storedStatus = accountStatusAfterCheck(storedStatus, status)
    } },
    ElMessage: message,
  }
  vm.runInNewContext(`${source}\nglobalThis.run = handleCheckAccount`, context)
  response = { code: 200, data: { status: 'unknown', message: '请查看账号窗口完成验证' } }
  await context.run({ id: 1 })
  assert.equal(storedStatus, '正常')
  assert.equal(notices.at(-1).message, response.data.message)
  response = new Error('该账号正在发布')
  await context.run({ id: 1 })
  assert.equal(storedStatus, '正常')
  assert.equal(notices.at(-1).message, '该账号正在发布')
  assert.equal(context.checkingIds.value.size, 0)
})

test('批量检查中的重登录遵循规范 SSE 终态，成功即更新账号，占用错误展示实际原因', () => {
  const source = section('components/AccountCheckDialog.vue', 'function startRelogin(card)', 'function cancelRelogin(card)')
    .replace('import.meta.env.VITE_API_BASE_URL', "'http://local.test'")
  const streams = []
  let storedStatus = '异常'
  let doneCount = 0
  const context = {
    crypto: { randomUUID: () => 'mock-login' },
    encodeURIComponent,
    eventSources: new Map(),
    EventSource: class {
      constructor(url) { this.url = url; streams.push(this) }
    },
    closeSSE: id => context.eventSources.delete(id),
    ElMessage: { success() {} },
    accountStore: { applyCheckStatus(_id, status) {
      storedStatus = accountStatusAfterCheck(storedStatus, status)
    } },
    checkAllFixed: () => { doneCount += 1 },
  }
  vm.runInNewContext(`${source}\nglobalThis.run = startRelogin`, context)
  const card = { id: 1, type: 5, name: '测试账号', resultStatus: 'invalid' }
  context.run(card)
  streams.at(-1).onmessage({ data: JSON.stringify({ status: 'progress' }) })
  assert.equal(card.fixStatus, 'logging')
  streams.at(-1).onmessage({ data: JSON.stringify({ status: 'success' }) })
  assert.equal(card.fixStatus, 'success')
  assert.equal(card.resultStatus, 'valid')
  assert.equal(storedStatus, '正常')
  assert.equal(doneCount, 1)
  assert.equal(context.eventSources.size, 0)
  streams.at(-1).onerror()
  assert.equal(card.fixStatus, 'success')

  context.run(card)
  streams.at(-1).onmessage({ data: JSON.stringify({ status: 'error', code: 'ACCOUNT_BUSY', msg: '该账号正在发布' }) })
  assert.equal(card.fixStatus, 'fail')
  assert.equal(card.fixError, '该账号正在发布')
  assert.equal(context.eventSources.size, 0)
})

test('提交结果未知作为终态停止轮询，只提示核实而不提示成功或自动重发', async () => {
  const statuses = section('views/PublishCenter.vue', 'const PREPARE_STATUS_VIEW =', 'const prepareSession =')
  const poller = section('views/PublishCenter.vue', 'async function pollPrepareSession(sessionId, generation)', 'async function restoreDraft(draftId)')
  const notices = []
  let calls = 0
  const context = {
    prepareSession: { value: { status: 'SUBMITTING' } },
    preparePollError: { value: '' },
    preparePollGeneration: 1,
    setTimeout(callback) { callback() },
    publishApi: { async getPrepareSession() {
      calls += 1
      return { data: { status: 'UNKNOWN', error: '请先核实是否提交成功，避免重复提交' } }
    } },
    ElMessage: Object.fromEntries(['success', 'error', 'warning', 'info'].map(type => [type, message => notices.push({ type, message })])),
  }
  vm.runInNewContext(`${statuses}\n${poller}\nglobalThis.run = pollPrepareSession`, context)
  await context.run('session-1', 1)
  assert.equal(calls, 1)
  assert.equal(context.prepareSession.value.status, 'UNKNOWN')
  assert.deepEqual(notices, [{ type: 'warning', message: '请先核实是否提交成功，避免重复提交' }])
})
