import test from 'node:test'
import assert from 'node:assert/strict'

import { desktopEnvironment } from '../shared/desktop-env.js'

test('桌面启动环境移除 ELECTRON_RUN_AS_NODE 污染', () => {
  const result = desktopEnvironment({ PATH: 'demo', ELECTRON_RUN_AS_NODE: '1' })
  assert.deepEqual(result, { PATH: 'demo' })
})
