import test from 'node:test'
import assert from 'node:assert/strict'

import {
  normalizeWordRows,
  safeDocxName,
} from '../shared/workflows.js'

test('Word 批量数据必须是对象数组', () => {
  assert.deepEqual(normalizeWordRows('[{"title":"第一篇"}]'), [{ title: '第一篇' }])
  assert.throws(() => normalizeWordRows('{"title":"第一篇"}'), /JSON 数组/)
  assert.throws(() => normalizeWordRows('[1]'), /对象/)
})

test('Word 输出文件名会移除 Windows 非法字符', () => {
  assert.equal(safeDocxName('深圳/招聘:夜班*'), '深圳_招聘_夜班_.docx')
})
