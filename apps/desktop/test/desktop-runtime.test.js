import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import path from 'node:path'
import test from 'node:test'

test('开发环境从 MATRIX_UI_URL 加载界面，生产环境只加载应用内 dist', async () => {
  const { resolveRendererEntry } = await import('../electron/main.js')
  const appPath = path.resolve('D:\\MatrixApp\\resources\\app.asar')

  assert.deepEqual(
    resolveRendererEntry({
      isPackaged: false,
      appPath,
      env: { MATRIX_UI_URL: 'http://127.0.0.1:4173' },
    }),
    { kind: 'url', value: 'http://127.0.0.1:4173' },
  )
  assert.deepEqual(
    resolveRendererEntry({
      isPackaged: true,
      appPath,
      env: { MATRIX_UI_URL: 'https://example.invalid/remote-ui' },
    }),
    {
      kind: 'file',
      value: path.join(
        appPath,
        'vendor',
        'social-auto-upload-web-ui',
        'frontend',
        'dist',
        'index.html',
      ),
    },
  )
})

test('窗口严格按入口类型调用 loadURL 或 loadFile', async () => {
  const { loadRendererEntry } = await import('../electron/main.js')
  const calls = []
  const window = {
    loadURL(value) { calls.push(['url', value]) },
    loadFile(value) { calls.push(['file', value]) },
  }

  await loadRendererEntry(window, { kind: 'url', value: 'http://127.0.0.1:5173' })
  await loadRendererEntry(window, { kind: 'file', value: 'D:\\MatrixApp\\app.asar\\dist\\index.html' })

  assert.deepEqual(calls, [
    ['url', 'http://127.0.0.1:5173'],
    ['file', 'D:\\MatrixApp\\app.asar\\dist\\index.html'],
  ])
})

test('生产后端运行时使用 resources/backend/runtime.json 清单且路径不得逃逸', async () => {
  const { resolvePackagedBackendContract } = await import('../electron/backend-runtime.js')
  const resourcesPath = path.resolve('D:\\MatrixApp\\resources')
  const contract = resolvePackagedBackendContract({
    resourcesPath,
    userDataPath: path.resolve('D:\\MatrixData'),
    manifest: {
      schemaVersion: 1,
      executable: 'python/python.exe',
      arguments: ['app.py'],
      workingDirectory: 'app',
      port: 5409,
    },
  })

  assert.equal(contract.executable, path.join(resourcesPath, 'backend', 'python', 'python.exe'))
  assert.deepEqual(contract.arguments, ['app.py'])
  assert.equal(contract.workingDirectory, path.join(resourcesPath, 'backend', 'app'))
  assert.equal(contract.healthUrl, 'http://127.0.0.1:5409/api/health')
  assert.equal(contract.environment.SAU_PORT, '5409')
  assert.equal(contract.environment.SAU_DATA_DIR, path.join('D:\\MatrixData', 'backend-data'))


  assert.throws(
    () => resolvePackagedBackendContract({
      resourcesPath,
      userDataPath: 'D:\\MatrixData',
      manifest: {
        schemaVersion: 1,
        executable: '../outside.exe',
        arguments: [],
        workingDirectory: 'app',
        port: 5409,
      },
    }),
    /后端运行时路径必须位于 backend 目录内/,
  )
})

test('生产后端未暂存清单时明确报错', async () => {
  const { readPackagedBackendContract } = await import('../electron/backend-runtime.js')

  assert.throws(
    () => readPackagedBackendContract({
      resourcesPath: path.resolve('D:\\MatrixApp\\resources'),
      userDataPath: path.resolve('D:\\MatrixData'),
      readFileSync() {
        const error = new Error('missing')
        error.code = 'ENOENT'
        throw error
      },
    }),
    /未暂存 Python 后端运行时/,
  )
})

test('生产后端按清单启动、通过健康检查后可随应用退出', async () => {
  const { startPackagedBackend } = await import('../electron/backend-runtime.js')
  const calls = []
  class FakeChild extends EventEmitter {
    killed = false

    kill() {
      this.killed = true
      this.emit('exit', 0)
      return true
    }
  }
  const child = new FakeChild()
  const contract = {
    executable: 'D:\\MatrixApp\\resources\\backend\\python\\python.exe',
    arguments: ['app.py'],
    workingDirectory: 'D:\\MatrixApp\\resources\\backend\\app',
    healthUrl: 'http://127.0.0.1:5409/api/health',
    environment: {
      SAU_PORT: '5409',
      SAU_DATA_DIR: 'D:\\MatrixData\\backend-data',
    },
  }

  const runtime = await startPackagedBackend({
    contract,
    environment: { PATH: 'demo' },
    spawnProcess(command, args, options) {
      calls.push({ command, args, options })
      return child
    },
    async fetchHealth(url) {
      calls.push({ health: url })
      return { ok: true }
    },
  })

  assert.equal(calls[0].command, contract.executable)
  assert.deepEqual(calls[0].args, contract.arguments)
  assert.equal(calls[0].options.cwd, contract.workingDirectory)
  assert.equal(calls[0].options.env.PATH, 'demo')
  assert.equal(calls[0].options.env.SAU_DATA_DIR, contract.environment.SAU_DATA_DIR)
  assert.equal(calls[0].options.env.SAU_PORT, contract.environment.SAU_PORT)
  assert.deepEqual(calls[1], { health: contract.healthUrl })
  await runtime.stop()
  assert.equal(child.killed, true)
})
