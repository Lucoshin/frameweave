import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { bundle } from '@remotion/bundler'
import { renderMedia, selectComposition } from '@remotion/renderer'
import { validateRenderStory } from './schema.mjs'

const emit = (event) => process.stdout.write(`${JSON.stringify(event)}\n`)
const project = path.dirname(fileURLToPath(import.meta.url))

function browserPath() {
  if (process.env.MATRIX_RENDER_BROWSER) {
    if (!existsSync(process.env.MATRIX_RENDER_BROWSER)) throw new Error('MATRIX_RENDER_BROWSER 指定的浏览器不存在')
    return process.env.MATRIX_RENDER_BROWSER
  }
  const candidates = [
    path.join(process.env['ProgramFiles(x86)'] || 'C:/Program Files (x86)', 'Microsoft/Edge/Application/msedge.exe'),
    path.join(process.env.ProgramFiles || 'C:/Program Files', 'Google/Chrome/Application/chrome.exe'),
  ]
  const browser = candidates.find(existsSync)
  if (!browser) throw new Error('未找到本机 Edge/Chrome，请安装浏览器或配置 MATRIX_RENDER_BROWSER')
  return browser
}

try {
  if (!process.argv[2]) throw new Error('需指定包含 story.json 和 assets 的任务目录')
  const directory = path.resolve(process.argv[2])
  const story = validateRenderStory(JSON.parse(await readFile(path.join(directory, 'story.json'), 'utf8')))
  const browserExecutable = browserPath()
  emit({ type: 'progress', progress: 0, message: '正在编译固定动画模板' })
  const serveUrl = await bundle({ entryPoint: path.join(project, 'src/index.jsx'), publicDir: path.join(directory, 'assets'), onProgress: percent => emit({ type: 'progress', progress: percent / 100 * 0.08, message: '正在编译固定动画模板' }) })
  const composition = await selectComposition({ serveUrl, id: 'MatrixAnimation', inputProps: story, browserExecutable, logLevel: 'error' })
  await renderMedia({ composition, serveUrl, codec: 'h264', outputLocation: path.join(directory, 'video.mp4'), inputProps: story, browserExecutable, concurrency: 2, logLevel: 'error', crf: 20,
    onProgress: ({ progress }) => emit({ type: 'progress', progress: 0.08 + progress * 0.92, message: '正在渲染并编码 MP4' }),
  })
  emit({ type: 'done', path: path.join(directory, 'video.mp4') })
} catch (error) {
  emit({ type: 'error', message: error.message })
  process.exitCode = 1
}
