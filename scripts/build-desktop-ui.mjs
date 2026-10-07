import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const REMOVE_TREE_OPTIONS = {
  recursive: true,
  force: true,
  maxRetries: 5,
  retryDelay: 200,
}

export function createDesktopUiBuildSpec({
  nodeExecutable = process.execPath,
  env = process.env,
  cwd = process.cwd(),
  buildId = `${process.pid}-${Date.now()}`,
} = {}) {
  if (!env.npm_execpath) {
    throw new Error('请通过 npm run build:ui:desktop 启动桌面界面构建')
  }
  const frontendDirectory = path.resolve(
    cwd,
    'vendor',
    'social-auto-upload-web-ui',
    'frontend',
  )
  const outputDirectory = path.join(frontendDirectory, 'dist')
  const stagingDirectory = path.join(frontendDirectory, `.matrix-dist-${buildId}`)
  return {
    command: nodeExecutable,
    arguments: [
      env.npm_execpath,
      '--prefix',
      'vendor/social-auto-upload-web-ui/frontend',
      'run',
      'build',
      '--',
      '--base=./',
      '--outDir',
      stagingDirectory,
      '--emptyOutDir',
    ],
    cwd,
    outputDirectory,
    stagingDirectory,
    environment: {
      ...env,
      VITE_API_BASE_URL: env.MATRIX_API_BASE_URL || 'http://127.0.0.1:5409',
    },
  }
}

function validateOutputPaths({ outputDirectory, stagingDirectory }) {
  if (path.basename(outputDirectory) !== 'dist') {
    throw new Error('桌面界面输出目录必须命名为 dist')
  }
  if (
    path.dirname(stagingDirectory) !== path.dirname(outputDirectory)
    || !path.basename(stagingDirectory).startsWith('.matrix-dist-')
  ) {
    throw new Error('桌面界面临时目录必须是 dist 同级的 .matrix-dist-* 目录')
  }
}

export async function replaceDesktopUiOutput({ outputDirectory, stagingDirectory }) {
  validateOutputPaths({ outputDirectory, stagingDirectory })
  const stagingIndex = path.join(stagingDirectory, 'index.html')
  const indexStat = await fs.promises.stat(stagingIndex)
  if (!indexStat.isFile()) throw new Error('桌面界面临时产物缺少 index.html')

  const backupDirectory = path.join(
    path.dirname(outputDirectory),
    `.matrix-dist-backup-${process.pid}-${Date.now()}`,
  )
  await fs.promises.rm(backupDirectory, REMOVE_TREE_OPTIONS)
  let oldOutputMoved = false
  try {
    try {
      await fs.promises.rename(outputDirectory, backupDirectory)
      oldOutputMoved = true
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error
    }
    await fs.promises.rename(stagingDirectory, outputDirectory)
  } catch (error) {
    if (oldOutputMoved) {
      try {
        await fs.promises.rename(backupDirectory, outputDirectory)
      } catch {
        // 保留原始替换错误；恢复失败时旧产物仍位于显式 backup 目录，避免静默覆盖。
      }
    }
    throw error
  }
  await fs.promises.rm(backupDirectory, REMOVE_TREE_OPTIONS)
}

function runBuildProcess(spec) {
  return new Promise((resolve, reject) => {
    const child = spawn(spec.command, spec.arguments, {
      cwd: spec.cwd,
      env: spec.environment,
      stdio: 'inherit',
      windowsHide: true,
    })
    child.once('error', reject)
    child.once('exit', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`桌面界面构建失败，退出码 ${code}`))
    })
  })
}

export async function buildDesktopUi(spec = createDesktopUiBuildSpec()) {
  validateOutputPaths(spec)
  await fs.promises.rm(spec.stagingDirectory, REMOVE_TREE_OPTIONS)
  try {
    await runBuildProcess(spec)
    await replaceDesktopUiOutput(spec)
  } catch (error) {
    try {
      await fs.promises.rm(spec.stagingDirectory, REMOVE_TREE_OPTIONS)
    } catch {
      // 清理失败不能覆盖真正的构建或替换错误。
    }
    throw error
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  buildDesktopUi().catch((error) => {
    console.error(error.message)
    process.exitCode = 1
  })
}
