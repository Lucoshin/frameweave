import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

test('前端 API 聚合文件只导出真实存在的模块', () => {
  const apiDirectory = path.resolve('vendor/social-auto-upload-web-ui/frontend/src/api')
  const source = readFileSync(path.join(apiDirectory, 'index.js'), 'utf8')
  const exports = source
    .split(/\r?\n/)
    .map((line) => line.match(/^export \* from ['"](.+)['"]/))
    .filter(Boolean)
    .map((match) => match[1])

  for (const modulePath of exports) {
    assert.equal(existsSync(path.join(apiDirectory, `${modulePath}.js`)), true, `缺少 API 模块 ${modulePath}.js`)
  }
})
