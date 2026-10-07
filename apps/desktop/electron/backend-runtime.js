import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'

function resolveInside(root, relativePath) {
  if (typeof relativePath !== 'string' || relativePath.length === 0 || path.isAbsolute(relativePath)) {
    throw new Error('后端运行时路径必须位于 backend 目录内')
  }
  const target = path.resolve(root, relativePath)
  const relation = path.relative(root, target)
  if (relation === '..' || relation.startsWith(`..${path.sep}`) || path.isAbsolute(relation)) {
    throw new Error('后端运行时路径必须位于 backend 目录内')
  }
  return target
}

export function resolvePackagedBackendContract({ resourcesPath, userDataPath, manifest }) {
  if (!manifest || manifest.schemaVersion !== 1) {
    throw new Error('Python 后端运行时清单 schemaVersion 必须为 1')
  }
  if (!Array.isArray(manifest.arguments) || manifest.arguments.some((item) => typeof item !== 'string')) {
    throw new Error('Python 后端运行时 arguments 必须是字符串数组')
  }
  if (!Number.isInteger(manifest.port) || manifest.port < 1024 || manifest.port > 65535) {
    throw new Error('Python 后端运行时 port 必须是 1024-65535 的整数')
  }

  const backendRoot = path.resolve(resourcesPath, 'backend')
  return {
    executable: resolveInside(backendRoot, manifest.executable),
    arguments: [...manifest.arguments],
    workingDirectory: resolveInside(backendRoot, manifest.workingDirectory),
    healthUrl: `http://127.0.0.1:${manifest.port}/api/health`,
    environment: {
      SAU_PORT: String(manifest.port),
      SAU_DATA_DIR: path.join(userDataPath, 'backend-data'),
    },
  }
}

export function readPackagedBackendContract({
  resourcesPath,
  userDataPath,
  readFileSync = fs.readFileSync,
}) {
  const manifestPath = path.join(resourcesPath, 'backend', 'runtime.json')
  let manifest
  try {
    manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  } catch (error) {
    if (error?.code === 'ENOENT') {
      throw new Error(`未暂存 Python 后端运行时：${manifestPath}`)
    }
    if (error instanceof SyntaxError) {
      throw new Error(`Python 后端运行时清单不是有效 JSON：${manifestPath}`)
    }
    throw error
  }
  return resolvePackagedBackendContract({ resourcesPath, userDataPath, manifest })
}

export async function startPackagedBackend({
  contract,
  environment = process.env,
  spawnProcess = spawn,
  fetchHealth = fetch,
  startupTimeoutMs = 30_000,
  pollIntervalMs = 200,
}) {
  const child = spawnProcess(contract.executable, contract.arguments, {
    cwd: contract.workingDirectory,
    env: { ...environment, ...contract.environment },
    stdio: 'ignore',
    windowsHide: true,
  })
  let startupFailure = null
  let running = true
  const onError = (error) => { startupFailure = error }
  const onExit = (code) => {
    running = false
    startupFailure ||= new Error(`Python 后端在就绪前退出，退出码 ${code}`)
  }
  child.once('error', onError)
  child.once('exit', onExit)

  const deadline = Date.now() + startupTimeoutMs
  try {
    while (Date.now() <= deadline) {
      if (startupFailure) throw startupFailure
      try {
        const response = await fetchHealth(contract.healthUrl)
        if (response.ok) {
          child.off('error', onError)
          child.off('exit', onExit)
          return {
            async stop() {
              if (!running) return
              running = false
              child.kill()
            },
          }
        }
      } catch (error) {
        if (startupFailure) throw startupFailure
      }
      await delay(pollIntervalMs)
    }
    throw new Error(`Python 后端启动超时：${contract.healthUrl}`)
  } catch (error) {
    child.off('error', onError)
    child.off('exit', onExit)
    if (running) child.kill()
    throw error
  }
}
