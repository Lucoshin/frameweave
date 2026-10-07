import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { mkdirSync } from 'node:fs'

import { readPackagedBackendContract, startPackagedBackend } from './backend-runtime.js'
import { createVideoEngineRunner } from './video-engine-runner.js'
import { generateWordBatch } from './workflow-runner.js'

const currentDir = path.dirname(fileURLToPath(import.meta.url))

export function resolveRendererEntry({ isPackaged, appPath, env = process.env }) {
  if (!isPackaged) {
    return { kind: 'url', value: env.MATRIX_UI_URL || 'http://127.0.0.1:5173' }
  }
  return {
    kind: 'file',
    value: path.join(
      appPath,
      'vendor',
      'social-auto-upload-web-ui',
      'frontend',
      'dist',
      'index.html',
    ),
  }
}

export function loadRendererEntry(window, entry) {
  if (entry.kind === 'url') return window.loadURL(entry.value)
  if (entry.kind === 'file') return window.loadFile(entry.value)
  throw new Error(`未知的界面入口类型：${entry.kind}`)
}

export function createVideoEngineRuntime({ app, env = process.env, resourcesPath = app.resourcesPath, runnerFactory = createVideoEngineRunner }) {
  const executablePath = app.isPackaged
    ? path.resolve(resourcesPath, 'video-engine', 'MaterialHarvester.Cli.exe')
    : env.MATRIX_VIDEO_ENGINE
  if (!executablePath) throw new Error('开发环境必须通过 MATRIX_VIDEO_ENGINE 指定视频引擎路径')
  return runnerFactory({ executablePath, jobRoot: path.join(app.getPath('userData'), 'video-engine-jobs') })
}

export function registerVideoEngineIpc({ ipcMain, dialog, videoRunner }) {
  const activeJobs = new Map()

  ipcMain.handle('video:choose-files', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openFile', 'multiSelections'],
      filters: [{ name: '视频', extensions: ['mp4', 'mov', 'mkv', 'avi', 'webm'] }],
    })
    return result.canceled ? [] : result.filePaths
  })
  ipcMain.handle('video:choose-output-directory', async () => {
    const result = await dialog.showOpenDialog({ properties: ['openDirectory', 'createDirectory'] })
    return result.canceled ? null : result.filePaths[0]
  })
  ipcMain.handle('video:start-job', async (event, request) => {
    if (!request || typeof request !== 'object') throw new TypeError('视频任务请求必须是对象')
    if (Object.hasOwn(request, 'executablePath')) throw new Error('渲染进程不能指定 executablePath')
    if (typeof request.jobId !== 'string' || request.jobId.length === 0) throw new Error('视频任务必须包含 jobId')
    if (activeJobs.has(request.jobId)) throw new Error(`视频任务已在运行：${request.jobId}`)

    const task = await videoRunner.start(request, {
      onEvent: (engineEvent) => event.sender.send('video:job-event', { jobId: request.jobId, event: engineEvent }),
    })
    activeJobs.set(request.jobId, task)
    try {
      return await task.completed
    } finally {
      if (activeJobs.get(request.jobId) === task) activeJobs.delete(request.jobId)
    }
  })
  ipcMain.handle('video:cancel-job', async (_event, jobId) => {
    const task = activeJobs.get(jobId)
    if (!task) throw new Error(`没有正在运行的视频任务：${jobId}`)
    await task.cancel()
    return { jobId, cancelRequested: true }
  })
}

function registerAppIpc({ ipcMain, dialog }) {
  ipcMain.handle('workflow:choose-word', async () => {
    const template = await dialog.showOpenDialog({ properties: ['openFile'], filters: [{ name: 'Word 模板', extensions: ['docx'] }] })
    if (template.canceled) return null
    const output = await dialog.showOpenDialog({ properties: ['openDirectory', 'createDirectory'] })
    if (output.canceled) return null
    return { templatePath: template.filePaths[0], outputDirectory: output.filePaths[0] }
  })
  ipcMain.handle('workflow:generate-word', (_event, payload) => generateWordBatch(payload))
}

function createMainWindow(BrowserWindow, rendererEntry) {
  const window = new BrowserWindow({
    width: 1512, height: 982, minWidth: 1180, minHeight: 760, show: false,
    icon: path.join(currentDir, '../assets/frameweave.ico'),
    title: '映织 · Frameweave',
    autoHideMenuBar: true, backgroundColor: '#f2f4f7', titleBarStyle: 'hiddenInset',
    webPreferences: { preload: path.join(currentDir, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  })
  window.once('ready-to-show', () => window.show())
  void loadRendererEntry(window, rendererEntry)
}

export async function bootstrapDesktop() {
  const electron = await import('electron')
  const { app, BrowserWindow, dialog, ipcMain } = electron.default ?? electron
  // 品牌改名不迁移账号、后端和素材数据；沿用原产品的 userData 目录。
  if (app.isPackaged) {
    const dataDirectory = path.join(app.getPath('appData'), '矩阵台')
    mkdirSync(dataDirectory, { recursive: true })
    app.setPath('userData', dataDirectory)
  }
  await app.whenReady()
  let backendRuntime = null
  if (app.isPackaged) {
    try {
      const contract = readPackagedBackendContract({
        resourcesPath: process.resourcesPath,
        userDataPath: app.getPath('userData'),
      })
      backendRuntime = await startPackagedBackend({ contract })
    } catch (error) {
      dialog.showErrorBox('映织启动失败', error.message)
      app.quit()
      return
    }
  }
  const rendererEntry = resolveRendererEntry({
    isPackaged: app.isPackaged,
    appPath: app.getAppPath(),
  })
  const videoRunner = createVideoEngineRuntime({ app, resourcesPath: process.resourcesPath })
  registerVideoEngineIpc({ ipcMain, dialog, videoRunner })
  registerAppIpc({ ipcMain, dialog })
  createMainWindow(BrowserWindow, rendererEntry)
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow(BrowserWindow, rendererEntry)
  })
  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit()
  })
  app.once('before-quit', () => {
    void backendRuntime?.stop()
  })
}

if (process.versions.electron) void bootstrapDesktop()
