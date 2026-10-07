import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const testDir = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(
  testDir,
  '../../../vendor/social-auto-upload-web-ui/frontend/src/views',
)
const frontendSourceDir = path.dirname(frontendDir)
const publishApiPath = path.join(frontendSourceDir, 'api', 'publish.js')
const requestPath = path.join(frontendSourceDir, 'utils', 'request.js')

test('发布 API 只暴露安全准备会话', async () => {
  assert.equal(existsSync(publishApiPath), true, '缺少发布 API 模块')
  const api = await readFile(publishApiPath, 'utf8')

  assert.match(api, /prepareVideo\s*\(data\)/)
  assert.match(api, /http\.post\(['"]\/api\/v2\/publish\/prepare['"],\s*data,\s*\{\s*matrixSilentErrors:\s*true/)
  assert.match(api, /getPrepareSession\s*\(sessionId\)/)
  assert.match(api, /\/api\/v2\/publish\/prepare\/\$\{encodeURIComponent\(sessionId\)\}/)
  assert.doesNotMatch(api, /getVideoTaskStatus/)
  assert.doesNotMatch(api, /postVideo/)
})

test('API 客户端接受后端 202 已受理响应', async () => {
  const request = await readFile(requestPath, 'utf8')
  assert.match(request, /data\.code === 202/)
})

test('静默请求抑制全局错误弹窗但仍向业务层 reject', async () => {
  const request = await readFile(requestPath, 'utf8')

  assert.match(request, /matrixSilentErrors/)
  assert.match(request, /if \(!silentErrors\)\s*\{\s*ElMessage\.error/s)
  assert.match(request, /return Promise\.reject\(error\)/)
})

test('启动准备与准备会话查询使用静默错误配置', async () => {
  const api = await readFile(publishApiPath, 'utf8')
  const silentUsages = api.match(/matrixSilentErrors:\s*true/g) || []

  assert.equal(silentUsages.length, 2, '启动准备与准备会话查询都应由业务层统一处理错误')
})

test('视频入口调用安全准备 API 并展示后端真实会话状态', async () => {
  const videoPage = await readFile(path.join(frontendDir, 'PublishCenter.vue'), 'utf8')

  assert.match(videoPage, /import \{ publishApi \} from ['"]@\/api\/publish['"]/)
  assert.match(videoPage, /publishApi\.prepareVideo\(/)
  assert.match(videoPage, /publishApi\.getPrepareSession\(/)
  assert.match(videoPage, /QUEUED/)
  assert.match(videoPage, /PREPARING/)
  assert.match(videoPage, /WAITING_CONFIRMATION/)
  assert.match(videoPage, /CLOSED/)
  assert.match(videoPage, /FAILED/)
  assert.match(videoPage, /手动点击发布/)
  assert.doesNotMatch(videoPage, /window\.matrixDesktop\.openAccountWindow/)
})

test('视频准备只开放已审计平台并沿用账号 cookie 与素材字段', async () => {
  const videoPage = await readFile(path.join(frontendDir, 'PublishCenter.vue'), 'utf8')

  assert.match(videoPage, /new Set\(\[1, 3, 5\]\)/)
  assert.match(videoPage, /fileList:\s*\[selectedVideo\.stored_path\]/)
  assert.match(videoPage, /accountList:\s*\[account\.filePath\]/)
  assert.match(videoPage, /resolveAccountConfig\(group\.key, account\.id\)/)
})

test('图集入口诚实标注未自动填充并复用后端账号环境', async () => {
  const imagePage = await readFile(path.join(frontendDir, 'ImagePublish.vue'), 'utf8')

  assert.match(imagePage, /保存并打开创作中心（不自动填充）/)
  assert.match(imagePage, /accountApi\.openCreatorCenter\(account\.id\)/)
  assert.doesNotMatch(imagePage, /window\.matrixDesktop\.openAccountWindow/)
  assert.doesNotMatch(imagePage, /publishApi\.prepareVideo/)
})

test('视频页面只轮询安全准备会话，不再轮询旧自动发布任务', async () => {
  const videoPage = await readFile(path.join(frontendDir, 'PublishCenter.vue'), 'utf8')

  assert.match(videoPage, /publishApi\.getPrepareSession\(sessionId\)/)
  assert.doesNotMatch(videoPage, /publishApi\.getVideoTaskStatus\(/)
  assert.doesNotMatch(videoPage, /fetch\(`\/postVideo\/status\//)
})

test('视频支持显式发布模式，图文仍保留手动创作中心入口', async () => {
  const [videoPage, imagePage] = await Promise.all([
    readFile(path.join(frontendDir, 'PublishCenter.vue'), 'utf8'),
    readFile(path.join(frontendDir, 'ImagePublish.vue'), 'utf8'),
  ])

  assert.match(videoPage, /@click="startPublishSession"/)
  assert.match(videoPage, /const publishMode = ref\('manual'\)/)
  assert.match(videoPage, /mode:\s*publishMode\.value/)
  assert.match(videoPage, /人工确认/)
  assert.match(videoPage, /自动发布/)
  assert.match(videoPage, /SUBMITTING/)
  assert.match(videoPage, /SUBMITTED/)
  assert.match(imagePage, /@click="prepareManualPublish"/)
  for (const page of [videoPage, imagePage]) {
    assert.doesNotMatch(page, /@click="publishAll"/)
    assert.doesNotMatch(page, />\s*一键发布\s*</)
  }
})

test('视频模式控件锁定运行中会话，状态标识取后端任务模式', async () => {
  const videoPage = await readFile(path.join(frontendDir, 'PublishCenter.vue'), 'utf8')
  assert.match(videoPage, /:disabled="publishModeLocked"/)
  assert.match(videoPage, /prepareSession\.mode === 'auto'/)
  assert.match(videoPage, /const publishModeLocked = computed/)
  assert.doesNotMatch(videoPage, /localStorage\.setItem\([^\n]*publishMode/)
})

test('视频与图文页面不再保留无入口的自动发布执行链', async () => {
  const [videoPage, imagePage] = await Promise.all([
    readFile(path.join(frontendDir, 'PublishCenter.vue'), 'utf8'),
    readFile(path.join(frontendDir, 'ImagePublish.vue'), 'utf8'),
  ])

  const obsoleteSymbols = [
    'BatchPublishDialog',
    'PrePublishCheckDialog',
    'batchPublishDialogVisible',
    'prePublishCheckRef',
    'prePublishCheckVisible',
    'publishing',
    'publishProgress',
    'publishResults',
    'currentPublishingAccount',
    'isCancelled',
    'publishAll',
    'cancelBatch',
  ]

  for (const page of [videoPage, imagePage]) {
    for (const symbol of obsoleteSymbols) {
      assert.doesNotMatch(page, new RegExp(`\\b${symbol}\\b`), `${symbol} 应随旧自动发布入口一起删除`)
    }
    assert.doesNotMatch(page, /panel\.publish\(/)
    assert.doesNotMatch(page, /@publish-result=/)
    assert.doesNotMatch(page, /:disabled="publishing"/)
    assert.doesNotMatch(page, /loadAccountCheckMode\(/)
  }

  assert.doesNotMatch(videoPage, /pollPublishStatus/)
  assert.doesNotMatch(videoPage, /http\.post\(['"]\/postVideo['"]/)
  assert.doesNotMatch(videoPage, /console\.log\(/)
  assert.doesNotMatch(videoPage, /\bcountDescriptionHashtags\b/)
  assert.doesNotMatch(videoPage, /\bDESC_HASHTAG_RE\b/)
  assert.doesNotMatch(videoPage, /import \{[^}]*\bnextTick\b[^}]*\} from ['"]vue['"]/)
  assert.doesNotMatch(imagePage, /function onPublishResult/)
})

test('草稿箱不再暴露旧批量发布链路并保留真实草稿操作', async () => {
  const draftPage = await readFile(path.join(frontendDir, 'DraftBox.vue'), 'utf8')

  const obsoletePublishSymbols = [
    'BatchDraftPublishDialog',
    'imagePublishApi',
    'dialogVisible',
    'dialogDrafts',
    'dialogFailures',
    'isPublishing',
    'onBatchPublish',
    'onDialogConfirm',
    'extractPlatforms',
    'batchPublishImageDrafts',
    'batchPublishVideoDrafts',
  ]

  assert.doesNotMatch(draftPage, /批量发布/)
  for (const symbol of obsoletePublishSymbols) {
    assert.doesNotMatch(draftPage, new RegExp(`\\b${symbol}\\b`), `${symbol} 应随旧批量发布入口一起删除`)
  }

  assert.match(draftPage, /@click="onBatchDelete"/)
  assert.match(draftPage, /draftApi\.batchDeleteDrafts\(ids\)/)
  assert.match(draftPage, /function editVideoDraft\(id\)/)
  assert.match(draftPage, /function editImageDraft\(id\)/)
  assert.match(draftPage, /draftApi\.deleteDraft\(id\)/)
})
