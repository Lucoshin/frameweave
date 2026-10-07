import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const testDir = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(testDir, '../../../vendor/social-auto-upload-web-ui/frontend')

test('桌面端使用映织原创品牌并默认亮色', async () => {
  const [html, config, store] = await Promise.all([
    readFile(path.join(frontendDir, 'index.html'), 'utf8'),
    readFile(path.join(frontendDir, 'src/config/app.js'), 'utf8'),
    readFile(path.join(frontendDir, 'src/stores/app.js'), 'utf8'),
  ])

  const visibleBrandSources = `${html}\n${config}`
  assert.doesNotMatch(visibleBrandSources, /千帆|QianFan/i)
  assert.match(visibleBrandSources, /映织/)
  assert.match(visibleBrandSources, /Frameweave/)
  assert.doesNotMatch(html, /<html[^>]*class="dark"/)
  assert.match(store, /const theme = ref\('light'\)/)
})

test('全局原创视觉层已接入且不再加载 Element Plus 暗色变量', async () => {
  const [main, originalSystem] = await Promise.all([
    readFile(path.join(frontendDir, 'src/main.js'), 'utf8'),
    readFile(path.join(frontendDir, 'src/styles/original-system.scss'), 'utf8'),
  ])

  assert.doesNotMatch(main, /theme-chalk\/dark\/css-vars\.css/)
  assert.match(main, /original-system\.scss/)
  assert.match(originalSystem, /var\(--accent-solid\)/)
  assert.doesNotMatch(originalSystem, /--matrix-blue:/)
  assert.match(originalSystem, /\.publish-workflow/)
  assert.doesNotMatch(originalSystem, /#0a0a1a|#12122a|#8b5cf6/i)
})
