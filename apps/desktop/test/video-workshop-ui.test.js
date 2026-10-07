import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { pathToFileURL } from 'node:url'

const viewPath = path.resolve('vendor/social-auto-upload-web-ui/frontend/src/views/VideoWorkshop.vue')
const helperPath = path.resolve('apps/desktop/shared/video-workshop.js')

test('视频工坊使用原创双模式工作区并移除未实现入口', async () => {
  const source = await readFile(viewPath, 'utf8')

  assert.match(source, /批量分割/)
  assert.match(source, /随机混剪/)
  assert.match(source, /activeMode/)
  assert.match(source, /智能场景/)
  assert.match(source, /固定时长/)
  assert.match(source, /Content/)
  assert.match(source, /Adaptive/)
  assert.match(source, /任务活动/)
  assert.match(source, /输出结果/)
  assert.doesNotMatch(source, /PySceneDetect|pyJianYingDraft|剪映草稿|去字幕/)
})

test('视频工坊通过受控桌面 API 选择批量文件、运行、接收事件并取消', async () => {
  const source = await readFile(viewPath, 'utf8')

  assert.match(source, /matrixDesktop\.chooseVideoFiles/)
  assert.match(source, /matrixDesktop\.chooseOutputDirectory/)
  assert.match(source, /matrixDesktop\.startVideoJob/)
  assert.match(source, /matrixDesktop\.cancelVideoJob/)
  assert.match(source, /matrixDesktop\.onVideoJobEvent/)
  assert.match(source, /onBeforeUnmount/)
  assert.match(source, /jobId/)
  assert.match(source, /result\.items/)
  assert.match(source, /item\.outputs/)
  assert.match(source, /item\.error/)
})

test('视频表单只生成版本化 split 和 compose 契约', async () => {
  assert.equal(existsSync(helperPath), true, '缺少视频工坊任务构造模块')
  const { createComposeJob, createSplitJob } = await import(pathToFileURL(helperPath))

  assert.deepEqual(createSplitJob({
    jobId: 'split-001',
    inputs: ['D:\\素材\\长视频.mp4'],
    outputDirectory: 'D:\\输出',
    mode: 'fixedDuration',
    durationSeconds: 8,
    selection: 'startAndEnd',
    mute: true,
    maxThreads: 2,
  }), {
    schemaVersion: 1,
    operation: 'split',
    jobId: 'split-001',
    inputs: ['D:\\素材\\长视频.mp4'],
    outputDirectory: 'D:\\输出',
    outputRule: 'perVideoSubfolder',
    split: { mode: 'fixedDuration', durationSeconds: 8, selection: 'startAndEnd' },
    encoding: { mode: 'auto', mute: true, maxThreads: 2 },
    subtitleRemoval: { enabled: false },
  })

  const compose = createComposeJob({
    jobId: 'compose-001',
    clips: ['a.mp4', 'b.mp4'],
    outputDirectory: 'out',
    outputCount: 1,
    clipsPerOutput: 2,
    maxParallelism: 1,
    muteAudio: false,
  })
  assert.equal(compose.operation, 'compose')
  assert.deepEqual(compose.subtitleRemoval, { enabled: false })
})

test('新视频引擎验收后清除旧命令、旧 IPC 和旧工具探测', async () => {
  const [mainSource, preloadSource, workflowSource, helperSource] = await Promise.all([
    readFile(path.resolve('apps/desktop/electron/main.js'), 'utf8'),
    readFile(path.resolve('apps/desktop/electron/preload.js'), 'utf8'),
    readFile(path.resolve('apps/desktop/electron/workflow-runner.js'), 'utf8'),
    readFile(path.resolve('apps/desktop/shared/workflows.js'), 'utf8'),
  ])
  const activeSource = [mainSource, preloadSource, workflowSource, helperSource].join('\n')

  assert.doesNotMatch(activeSource, /workflow:choose-video|workflow:split-video|chooseVideoWorkflow|buildSceneDetectArgs|scenedetect/)
  assert.equal(existsSync(path.resolve('apps/desktop/electron/tool-runner.js')), false)
  assert.equal(existsSync(path.resolve('apps/desktop/shared/tools.js')), false)
})
