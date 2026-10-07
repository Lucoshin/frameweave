import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'

import { createVideoEngineRunner } from '../electron/video-engine-runner.js'
import { buildComposeRequest, buildSplitRequest } from '../shared/video-engine-contract.js'

const fakeCliSource = String.raw`
import { access, appendFile, readFile, writeFile } from 'node:fs/promises'
import { setTimeout as wait } from 'node:timers/promises'

const [command, ...rawArguments] = process.argv.slice(2)
const argument = (name) => rawArguments[rawArguments.indexOf(name) + 1]
const requestPath = argument('--request')
const eventsPath = argument('--events')
const resultPath = argument('--result')
const cancelPath = argument('--cancel')
const request = JSON.parse(await readFile(requestPath, 'utf8'))

await appendFile(eventsPath, JSON.stringify({ type: 'stage', stage: 'analyzing' }) + '\n')

if (request.jobId === 'cancel-job') {
  await appendFile(eventsPath, JSON.stringify({ type: 'ready-for-cancel' }) + '\n')
  for (let attempt = 0; attempt < 500; attempt += 1) {
    try {
      await access(cancelPath)
      await writeFile(resultPath, JSON.stringify({ status: 'cancelled', cancelSignalObserved: true }))
      process.exit(0)
    } catch {
      await wait(10)
    }
  }
  process.exit(9)
}

await appendFile(eventsPath, JSON.stringify({ type: 'progress', current: 1, total: 1 }) + '\n')
if (request.jobId === 'invalid-result-job') {
  await writeFile(resultPath, 'null')
  process.exit(4)
}
if (request.jobId === 'failed-result-job') {
  await writeFile(resultPath, JSON.stringify({
    status: 'failed',
    items: [{ input: request.inputs[0], status: 'failed', error: '素材损坏' }],
  }))
  process.exit(4)
}
await writeFile(resultPath, JSON.stringify({
  status: 'succeeded',
  command,
  receivedRequest: request,
}))
`

async function createFixture(t) {
  const root = await mkdtemp(path.join(tmpdir(), 'matrix-video-engine-runner-'))
  const fakeCliPath = path.join(root, 'fake-video-engine.mjs')
  const jobsPath = path.join(root, 'jobs')
  await writeFile(fakeCliPath, fakeCliSource)
  t.after(() => rm(root, { recursive: true, force: true }))

  return createVideoEngineRunner({
    executablePath: process.execPath,
    executableArguments: [fakeCliPath],
    jobRoot: jobsPath,
    eventPollIntervalMs: 5,
  })
}

function splitRequest(jobId) {
  return buildSplitRequest({
    jobId,
    inputs: ['D:\\素材\\原片 01.mp4'],
    outputDirectory: 'D:\\输出 目录',
    mode: 'smartScene',
    sceneEngine: 'adaptive',
    sensitivity: 0.75,
    minimumSceneDurationSeconds: 10,
    maxThreads: 3,
  })
}

function composeRequest(jobId) {
  return buildComposeRequest({
    jobId,
    clips: ['D:\\素材\\片段 01.mp4', 'D:\\素材\\片段 02.mp4'],
    outputDirectory: 'D:\\混剪输出',
    outputCount: 2,
    clipsPerOutput: 2,
    maxParallelism: 1,
  })
}

test('runner 写入 JSON 请求、读取 JSONL 事件和最终结果', async (t) => {
  const runner = await createFixture(t)
  const request = {
    ...splitRequest('normal-job'),
    executablePath: 'D:\\不应被执行\\attacker.exe',
  }
  const events = []

  const task = await runner.start(request, {
    onEvent: (event) => events.push(event),
  })
  const result = await task.completed

  assert.equal(result.status, 'succeeded')
  assert.equal(result.command, 'split')
  assert.deepEqual(result.receivedRequest, request)
  assert.deepEqual(events, [
    { type: 'stage', stage: 'analyzing' },
    { type: 'progress', current: 1, total: 1 },
  ])
})

test('runner 取消任务时只写取消信号并等待引擎正常收尾', async (t) => {
  const runner = await createFixture(t)
  let readyForCancel
  const ready = new Promise((resolve) => { readyForCancel = resolve })
  const task = await runner.start(splitRequest('cancel-job'), {
    onEvent(event) {
      if (event.type === 'ready-for-cancel') readyForCancel()
    },
  })

  await ready
  await task.cancel()
  const result = await task.completed

  assert.deepEqual(result, {
    status: 'cancelled',
    cancelSignalObserved: true,
  })
})

test('runner 根据 compose 请求调用对应 CLI 命令', async (t) => {
  const runner = await createFixture(t)
  const request = composeRequest('compose-job')

  const task = await runner.start(request)
  const result = await task.completed

  assert.equal(result.command, 'compose')
  assert.deepEqual(result.receivedRequest, request)
})

test('引擎退出码非零时仍返回合法的失败结果详情', async (t) => {
  const runner = await createFixture(t)
  const task = await runner.start(splitRequest('failed-result-job'))

  const result = await task.completed

  assert.deepEqual(result, {
    status: 'failed',
    items: [{
      input: 'D:\\素材\\原片 01.mp4',
      status: 'failed',
      error: '素材损坏',
    }],
  })
})

test('引擎结果不是带状态的对象时按无效结果抛错', async (t) => {
  const runner = await createFixture(t)
  const task = await runner.start(splitRequest('invalid-result-job'))

  await assert.rejects(task.completed, /没有生成有效结果/)
})
