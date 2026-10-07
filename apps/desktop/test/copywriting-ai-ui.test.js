import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { pathToFileURL } from 'node:url'

const frontendDir = path.resolve('vendor/social-auto-upload-web-ui/frontend/src')
const viewPath = path.join(frontendDir, 'views/CopywritingCenter.vue')
const apiPath = path.join(frontendDir, 'api/word.js')
const helperPath = path.join(frontendDir, 'utils/word-generation.js')

test('文案中心提供 AI 成文与模板套打两个清晰模式', async () => {
  const source = await readFile(viewPath, 'utf8')

  assert.match(source, /AI 批量成文/)
  assert.match(source, /模板套打/)
  assert.match(source, /activeMode/)
  assert.match(source, /v-model="titlesText"/)
  assert.match(source, /v-model="aiConfig\.prompt"/)
  assert.match(source, /useAiStore/)
  assert.match(source, /getTextConfig/)
  assert.doesNotMatch(source, /v-model="aiConfig\.(apiKey|baseUrl|model)"/)
})

test('图文成文提交所选图片来源，纯文字不携带图片配置', async () => {
  const { buildWordGenerationPayload } = await import(pathToFileURL(helperPath))
  const args = { titlesText: '文章', prompt: '要求', outputDirectory: 'D:\\out', baseUrl: 'https://example.invalid/v1', apiKey: 'text-key', model: 'text-model' }
  assert.equal(buildWordGenerationPayload(args).images, undefined)
  const images = { mode: 'ai', count: 2, prompt: '扁平插画', provider: { baseUrl: 'https://image.invalid/v1', apiKey: 'image-key', model: 'image-model' } }
  assert.deepEqual(buildWordGenerationPayload({ ...args, images }).images, images)
})

test('图文模式保留本地配图与独立图像服务选择', async () => {
  const source = await readFile(viewPath, 'utf8')
  assert.match(source, /纯文字/)
  assert.match(source, /图文/)
  assert.match(source, /本地图片/)
  assert.match(source, /AI 生成/)
  assert.match(source, /getImageConfig/)
  assert.match(source, /item\.image_paths/)
})

test('AI 成文调用约定接口并展示逐篇成功或错误结果', async () => {
  assert.equal(existsSync(apiPath), true, '缺少 Word AI 前端 API 模块')
  const [viewSource, apiSource] = await Promise.all([
    readFile(viewPath, 'utf8'),
    readFile(apiPath, 'utf8'),
  ])

  assert.match(apiSource, /http\.post\(['"]\/api\/v2\/word\/generate['"]/)
  assert.match(viewSource, /wordApi\.generate/)
  assert.match(viewSource, /result\.items/)
  assert.match(viewSource, /item\.error/)
  assert.match(viewSource, /item\.output_path/)
  assert.match(viewSource, /AI 生成失败/)
})

test('标题解析忽略空行但保留重复标题，提交体严格匹配后端字段', async () => {
  assert.equal(existsSync(helperPath), true, '缺少 Word AI 表单契约辅助模块')
  const { buildWordGenerationPayload, parseTitleLines } = await import(pathToFileURL(helperPath))

  assert.deepEqual(parseTitleLines(' 第一篇\n\n第二篇\r\n第一篇 '), ['第一篇', '第二篇', '第一篇'])
  assert.deepEqual(buildWordGenerationPayload({
    titlesText: '第一篇\n第二篇',
    prompt: ' 写得自然 ',
    outputDirectory: ' D:\\output ',
    providerId: ' custom ',
    baseUrl: ' https://api.example.com/v1 ',
    apiKey: ' secret ',
    model: ' model-a ',
    includeTitle: false,
  }), {
    titles: ['第一篇', '第二篇'],
    prompt: '写得自然',
    output_directory: 'D:\\output',
    provider: {
      provider_id: 'custom',
      base_url: 'https://api.example.com/v1',
      api_key: 'secret',
      model: 'model-a',
    },
    include_title: false,
  })
})

test('API Key 不写入浏览器持久存储且模板套打能力仍保留', async () => {
  const source = await readFile(viewPath, 'utf8')

  assert.doesNotMatch(source, /localStorage|sessionStorage/)
  assert.match(source, /matrixDesktop\.chooseWordWorkflow/)
  assert.match(source, /matrixDesktop\.generateWordBatch/)
  assert.match(source, /jsonText/)
  assert.match(source, /filenameField/)
})

test('AI Word 保存目录通过桌面目录选择器获取', async () => {
  const source = await readFile(viewPath, 'utf8')

  assert.match(source, /matrixDesktop\.chooseOutputDirectory/)
  assert.match(source, /chooseAiOutputDirectory/)
  assert.match(source, /选择目录/)
})
