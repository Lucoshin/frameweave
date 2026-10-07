import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'

const frontendDir = path.resolve('vendor/social-auto-upload-web-ui/frontend')
const apiDir = path.join(frontendDir, 'src', 'api')
const sourceDir = path.join(frontendDir, 'src')
const imagePanelPaths = [
  ['douyin', 'ImagePublishPanel.vue'],
  ['xiaohongshu', 'ImagePublishPanel.vue'],
  ['kuaishou', 'ImagePublishPanel.vue'],
  ['weibo', 'ImagePublishPanel.vue'],
  ['alipay', 'ImagePublishPanel.vue'],
  ['weixin_gzh', 'ImagePublishPanel.vue'],
].map(parts => path.join(sourceDir, 'components', ...parts))

async function readApi(name) {
  return readFile(path.join(apiDir, `${name}.js`), 'utf8')
}

test('前端 API 不再暴露无人调用的旧自动发布链路', async () => {
  const [draftApi, imagePublishApi, v2Api] = await Promise.all([
    readApi('draft'),
    readApi('imagePublish'),
    readApi('v2'),
  ])

  assert.doesNotMatch(draftApi, /batchPublishVideoDrafts/)
  assert.doesNotMatch(draftApi, /\/api\/v2\/drafts\/batch-publish/)
  assert.doesNotMatch(imagePublishApi, /batchPublishImageDrafts/)
  assert.doesNotMatch(imagePublishApi, /\/api\/image-publish\/drafts\/batch-publish/)
  assert.doesNotMatch(imagePublishApi, /execute-publish/)
  assert.doesNotMatch(v2Api, /export const taskApi/)
  assert.doesNotMatch(v2Api, /\/api\/v2\/tasks/)
  assert.doesNotMatch(v2Api, /\/api\/v2\/queue\/status/)
})

test('半自动准备、草稿 CRUD 与图集手动跳转所需接口保持可用', async () => {
  const [publishApi, draftApi, imagePublishApi, accountApi, viteConfig] = await Promise.all([
    readApi('publish'),
    readApi('draft'),
    readApi('imagePublish'),
    readApi('account'),
    readFile(path.join(frontendDir, 'vite.config.js'), 'utf8'),
  ])

  assert.match(publishApi, /prepareVideo\s*\(data\)/)
  assert.match(publishApi, /getPrepareSession\s*\(sessionId\)/)

  for (const method of ['getDrafts', 'createDraft', 'getDraft', 'updateDraft', 'deleteDraft', 'batchDeleteDrafts']) {
    assert.match(draftApi, new RegExp(`\\b${method}\\s*\\(`), `视频草稿接口缺少 ${method}`)
  }
  for (const method of ['getDrafts', 'saveDraft', 'deleteDraft']) {
    assert.match(imagePublishApi, new RegExp(`\\b${method}\\s*\\(`), `图集草稿接口缺少 ${method}`)
  }

  assert.match(accountApi, /openCreatorCenter\s*\(id\)/)
  assert.match(viteConfig, /['"]\/openCreatorCenter['"]\s*:/)
  assert.match(viteConfig, /['"]\/api['"]\s*:/)
})

test('Vite 不再为旧视频自动发布端点配置专用代理', async () => {
  const viteConfig = await readFile(path.join(frontendDir, 'vite.config.js'), 'utf8')

  assert.doesNotMatch(viteConfig, /['"]\/postVideo['"]\s*:/)
  assert.doesNotMatch(viteConfig, /['"]\/postVideoBatch['"]\s*:/)
})

test('图集面板与旧 store 不再保留不可达的自动发布执行链', async () => {
  const [imagePublishApi, channelForm, imagePublishStore, ...panels] = await Promise.all([
    readApi('imagePublish'),
    readFile(path.join(sourceDir, 'composables', 'useChannelForm.js'), 'utf8'),
    readFile(path.join(sourceDir, 'stores', 'imagePublish.js'), 'utf8'),
    ...imagePanelPaths.map(panelPath => readFile(panelPath, 'utf8')),
  ])

  assert.doesNotMatch(imagePublishApi, /publishImage\s*\(/)
  assert.doesNotMatch(imagePublishApi, /\/api\/image-publish\/publish/)
  assert.doesNotMatch(channelForm, /\bpublishFn\b/)
  assert.doesNotMatch(channelForm, /async publish\s*\(/)
  assert.doesNotMatch(imagePublishStore, /imagePublishApi\.publishImage\s*\(/)
  assert.doesNotMatch(imagePublishStore, /async function publish\s*\(/)
  assert.doesNotMatch(imagePublishStore, /\bpublishing\s*[,=]/)

  for (const panel of panels) {
    assert.doesNotMatch(panel, /imagePublishApi/)
    assert.doesNotMatch(panel, /useAccountStore/)
    assert.doesNotMatch(panel, /\bpublishFn\b/)
    assert.doesNotMatch(panel, /publish-result/)
  }
})

test('删除图集自动发布死链后仍保留面板配置与草稿手动流程', async () => {
  const [channelForm, imagePage, imagePublishApi, ...panels] = await Promise.all([
    readFile(path.join(sourceDir, 'composables', 'useChannelForm.js'), 'utf8'),
    readFile(path.join(sourceDir, 'views', 'ImagePublish.vue'), 'utf8'),
    readApi('imagePublish'),
    ...imagePanelPaths.map(panelPath => readFile(panelPath, 'utf8')),
  ])

  for (const method of ['getConfigs', 'restoreConfigs', 'setPlatformConfig', 'setAccountOverride']) {
    assert.match(channelForm, new RegExp(`\\b${method}\\s*\\(`), `面板配置接口缺少 ${method}`)
  }
  for (const panel of panels) {
    assert.match(panel, /defineExpose\(publicApi\)/)
    assert.match(panel, /defineEmits\(\[['"]config-changed['"]\]\)/)
  }

  assert.match(imagePublishApi, /saveDraft\s*\(data\)/)
  assert.match(imagePage, /panel\.getConfigs\(\)/)
  assert.match(imagePage, /panel\.restoreConfigs\(/)
  assert.match(imagePage, /imagePublishApi\.saveDraft\(/)
  assert.match(imagePage, /accountApi\.openCreatorCenter\(account\.id\)/)
})
