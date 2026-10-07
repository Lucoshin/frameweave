import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const pythonPath = path.resolve('vendor/social-auto-upload-web-ui/backend/.venv/Scripts/python.exe')
const backendDirectory = path.resolve('vendor/social-auto-upload-web-ui/backend')
const testData = fs.mkdtempSync(path.join(os.tmpdir(), 'matrix-backend-tests-'))
// app 导入会初始化数据库；回归测试始终使用独立数据目录，不接触运营数据。
const tests = [
  'test_semi_auto_guard.py', 'test_prepare_publish_service.py',
  'test_prepare_publish_api.py', 'test_prepare_platform_guards.py',
  'test_ai_word_service.py', 'test_ai_word_api.py', 'test_ai_images.py',
  'test_animation.py', 'test_speech.py',
  'test_account_operations.py', 'test_account_operation_api.py',
  'test_picker_lifecycle.py', 'test_session_log_privacy.py',
  'test_settings_session_migration.py', 'test_cookie_import_transaction.py',
  'test_metadata_readonly.py', 'test_bilibili_required_fields.py',
  'test_browser_close_cancel.py',
  'test_browser_installation.py', 'test_login_sessions.py', 'test_login_sse_stream.py',
]
try {
  const result = spawnSync(pythonPath, ['-m', 'pytest', '-q', '-p', 'no:cacheprovider',
    `--basetemp=${path.join(testData, 'pytest')}`, ...tests.map(name => `tests/${name}`)], {
    cwd: backendDirectory,
    env: { ...process.env, SAU_DATA_DIR: testData, PYTHONPATH: backendDirectory },
    stdio: 'inherit',
  })
  process.exitCode = result.status ?? 1
} finally {
  const relative = path.relative(path.resolve(os.tmpdir()), path.resolve(testData))
  if (!relative.startsWith('..') && !path.isAbsolute(relative) && path.basename(testData).startsWith('matrix-backend-tests-')) {
    fs.rmSync(testData, { recursive: true, force: true })
  }
}
