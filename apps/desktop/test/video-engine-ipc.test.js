import assert from 'node:assert/strict'
import test from 'node:test'
import path from 'node:path'

class FakeIpcMain {
  constructor() {
    this.handlers = new Map()
  }

  handle(channel, handler) {
    this.handlers.set(channel, handler)
  }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

test('视频引擎路径开发期只读环境变量，生产期只读 resourcesPath 固定位置', async () => {
  const { createVideoEngineRuntime } = await import('../electron/main.js')
  const creations = []
  const runnerFactory = (options) => {
    creations.push(options)
    return { start() {} }
  }
  const userDataPath = path.resolve('D:\\matrix-user-data')
  const devExecutable = path.resolve('D:\\dev-engine\\MaterialHarvester.Cli.exe')

  const devRunner = createVideoEngineRuntime({
    app: {
      isPackaged: false,
      resourcesPath: path.resolve('D:\\ignored-resources'),
      getPath: () => userDataPath,
    },
    env: { MATRIX_VIDEO_ENGINE: devExecutable },
    runnerFactory,
  })
  assert.equal(devRunner.start instanceof Function, true)
  assert.equal(creations[0].executablePath, devExecutable)

  createVideoEngineRuntime({
    app: {
      isPackaged: true,
      resourcesPath: path.resolve('D:\\MatrixApp\\resources'),
      getPath: () => userDataPath,
    },
    env: { MATRIX_VIDEO_ENGINE: path.resolve('D:\\attacker.exe') },
    runnerFactory,
  })

  assert.equal(
    creations[1].executablePath,
    path.resolve('D:\\MatrixApp\\resources', 'video-engine', 'MaterialHarvester.Cli.exe'),
  )
  assert.equal(creations[1].jobRoot, path.join(userDataPath, 'video-engine-jobs'))
})

test('视频 IPC 选择多文件和独立输出目录', async () => {
  const { registerVideoEngineIpc } = await import('../electron/main.js')
  const ipcMain = new FakeIpcMain()
  const calls = []
  const dialog = {
    async showOpenDialog(options) {
      calls.push(options)
      if (options.properties.includes('multiSelections')) {
        return { canceled: false, filePaths: ['D:\\素材\\一.mp4', 'D:\\素材\\二.mov'] }
      }
      return { canceled: false, filePaths: ['D:\\输出'] }
    },
  }

  registerVideoEngineIpc({
    ipcMain,
    dialog,
    videoRunner: { start() { throw new Error('本测试不应启动任务') } },
  })

  assert.deepEqual(await ipcMain.handlers.get('video:choose-files')(), [
    'D:\\素材\\一.mp4',
    'D:\\素材\\二.mov',
  ])
  assert.equal(await ipcMain.handlers.get('video:choose-output-directory')(), 'D:\\输出')
  assert.deepEqual(calls[0].properties, ['openFile', 'multiSelections'])
  assert.deepEqual(calls[1].properties, ['openDirectory', 'createDirectory'])
})

test('split 和 compose 任务统一启动并把引擎事件转发给发起窗口', async () => {
  const { registerVideoEngineIpc } = await import('../electron/main.js')

  for (const operation of ['split', 'compose']) {
    const ipcMain = new FakeIpcMain()
    const requests = []
    const sends = []
    const videoRunner = {
      async start(request, { onEvent }) {
        requests.push(request)
        onEvent({ type: 'progress', current: 1, total: 2 })
        return {
          completed: Promise.resolve({ status: 'succeeded', operation }),
          async cancel() {},
        }
      },
    }
    registerVideoEngineIpc({ ipcMain, dialog: {}, videoRunner })
    const request = { schemaVersion: 1, operation, jobId: `${operation}-job` }
    const event = { sender: { send: (...args) => sends.push(args) } }

    const result = await ipcMain.handlers.get('video:start-job')(event, request)

    assert.deepEqual(requests, [request])
    assert.deepEqual(result, { status: 'succeeded', operation })
    assert.deepEqual(sends, [[
      'video:job-event',
      {
        jobId: `${operation}-job`,
        event: { type: 'progress', current: 1, total: 2 },
      },
    ]])
  }
})

test('视频 IPC 可取消仍在运行的任务', async () => {
  const { registerVideoEngineIpc } = await import('../electron/main.js')
  const ipcMain = new FakeIpcMain()
  const completion = deferred()
  let cancelCount = 0
  const videoRunner = {
    async start() {
      return {
        completed: completion.promise,
        async cancel() { cancelCount += 1 },
      }
    },
  }
  registerVideoEngineIpc({ ipcMain, dialog: {}, videoRunner })
  const startPromise = ipcMain.handlers.get('video:start-job')(
    { sender: { send() {} } },
    { schemaVersion: 1, operation: 'split', jobId: 'cancel-job' },
  )
  await Promise.resolve()

  const cancelResult = await ipcMain.handlers.get('video:cancel-job')({}, 'cancel-job')
  completion.resolve({ status: 'cancelled' })

  assert.deepEqual(cancelResult, { jobId: 'cancel-job', cancelRequested: true })
  assert.equal(cancelCount, 1)
  assert.deepEqual(await startPromise, { status: 'cancelled' })
})

test('渲染进程不能通过任务请求覆盖视频引擎可执行路径', async () => {
  const { registerVideoEngineIpc } = await import('../electron/main.js')
  const ipcMain = new FakeIpcMain()
  let started = false
  registerVideoEngineIpc({
    ipcMain,
    dialog: {},
    videoRunner: {
      async start() {
        started = true
        throw new Error('不应执行')
      },
    },
  })

  await assert.rejects(
    ipcMain.handlers.get('video:start-job')(
      { sender: { send() {} } },
      {
        schemaVersion: 1,
        operation: 'split',
        jobId: 'unsafe-job',
        executablePath: 'D:\\attacker.exe',
      },
    ),
    /不能指定 executablePath/,
  )
  assert.equal(started, false)
})

test('preload 只暴露当前视频任务方法并支持事件退订', async () => {
  const { createDesktopApi } = await import('../electron/preload.js')
  const invokes = []
  const listeners = new Map()
  const ipcRenderer = {
    invoke(channel, ...args) {
      invokes.push([channel, ...args])
      return Promise.resolve(channel)
    },
    on(channel, listener) {
      listeners.set(channel, listener)
    },
    removeListener(channel, listener) {
      if (listeners.get(channel) === listener) listeners.delete(channel)
    },
  }
  const api = createDesktopApi(ipcRenderer)
  const request = { operation: 'compose', jobId: 'compose-job' }

  await api.chooseVideoFiles()
  await api.chooseOutputDirectory()
  await api.startVideoJob(request)
  await api.cancelVideoJob('compose-job')

  assert.deepEqual(invokes, [
    ['video:choose-files'],
    ['video:choose-output-directory'],
    ['video:start-job', request],
    ['video:cancel-job', 'compose-job'],
  ])
  assert.equal('chooseVideoWorkflow' in api, false)
  assert.equal('splitVideo' in api, false)
  assert.equal('getToolStatuses' in api, false)

  const received = []
  const unsubscribe = api.onVideoJobEvent((payload) => received.push(payload))
  listeners.get('video:job-event')({}, { jobId: 'compose-job', event: { type: 'progress' } })
  assert.deepEqual(received, [{ jobId: 'compose-job', event: { type: 'progress' } }])
  unsubscribe()
  assert.equal(listeners.has('video:job-event'), false)
})
