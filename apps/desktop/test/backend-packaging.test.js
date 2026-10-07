import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

test('后端便携运行时参数只来自显式命令行或环境变量', async () => {
  const {
    REMOVE_TREE_OPTIONS,
    resolveBackendRuntimeBuild,
  } = await import('../../../scripts/build-backend-runtime.mjs')
  const cwd = path.resolve('C:\\MatrixWorkspace')

  assert.deepEqual(REMOVE_TREE_OPTIONS, {
    recursive: true,
    force: true,
    maxRetries: 5,
    retryDelay: 200,
  })

  assert.deepEqual(
    resolveBackendRuntimeBuild({
      argv: ['--backend-source', 'backend-source'],
      env: {
        MATRIX_PYTHON_ROOT: 'python-portable',
        MATRIX_PYTHON_SITE_PACKAGES: 'prepared-site-packages',
      },
      cwd,
    }),
    {
      pythonRoot: path.join(cwd, 'python-portable'),
      sitePackages: path.join(cwd, 'prepared-site-packages'),
      backendSource: path.join(cwd, 'backend-source'),
      destination: path.join(cwd, 'build-resources', 'backend'),
      port: 5409,
    },
  )

  assert.throws(
    () => resolveBackendRuntimeBuild({ argv: [], env: {}, cwd }),
    /--python-root 或 MATRIX_PYTHON_ROOT/,
  )
  assert.throws(
    () => resolveBackendRuntimeBuild({
      argv: ['--python-root', 'python'],
      env: {},
      cwd,
    }),
    /--site-packages 或 MATRIX_PYTHON_SITE_PACKAGES/,
  )
  assert.throws(
    () => resolveBackendRuntimeBuild({
      argv: ['--python-root', 'python', '--site-packages', 'packages'],
      env: {},
      cwd,
    }),
    /--backend-source 或 MATRIX_BACKEND_SOURCE/,
  )
})

test('后端便携运行时生成清单并排除开发缓存、测试和本地数据', async (context) => {
  const { buildBackendRuntime } = await import('../../../scripts/build-backend-runtime.mjs')
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'matrix-backend-stage-'))
  context.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }))

  const pythonRoot = path.join(tempRoot, 'python-source')
  const sitePackages = path.join(tempRoot, 'site-packages')
  const backendSource = path.join(tempRoot, 'backend-source')
  const destination = path.join(tempRoot, 'resources', 'backend')
  fs.mkdirSync(path.join(pythonRoot, 'Lib', 'site-packages', 'old-package'), { recursive: true })
  fs.writeFileSync(path.join(pythonRoot, 'python.exe'), 'python')
  fs.writeFileSync(path.join(pythonRoot, 'python311.dll'), 'dll')
  fs.writeFileSync(path.join(pythonRoot, 'Lib', 'site-packages', 'old-package', 'old.py'), 'old')

  fs.mkdirSync(path.join(sitePackages, 'runtime_package'), { recursive: true })
  fs.mkdirSync(path.join(sitePackages, 'runtime_package-1.0.dist-info'), { recursive: true })
  fs.mkdirSync(path.join(sitePackages, 'runtime_package', 'tests'), { recursive: true })
  fs.mkdirSync(path.join(sitePackages, 'runtime_package', '__pycache__'), { recursive: true })
  fs.writeFileSync(path.join(sitePackages, 'runtime_package', '__init__.py'), 'runtime = True')
  fs.writeFileSync(path.join(sitePackages, 'runtime_package-1.0.dist-info', 'LICENSE'), 'MIT')
  fs.writeFileSync(path.join(sitePackages, 'runtime_package', 'tests', 'test_runtime.py'), 'drop')
  fs.writeFileSync(path.join(sitePackages, 'runtime_package', '__pycache__', 'cached.pyc'), 'drop')

  fs.mkdirSync(path.join(backendSource, 'services'), { recursive: true })
  fs.mkdirSync(path.join(backendSource, '.venv'), { recursive: true })
  fs.mkdirSync(path.join(backendSource, 'tests'), { recursive: true })
  fs.mkdirSync(path.join(backendSource, '__pycache__'), { recursive: true })
  fs.mkdirSync(path.join(backendSource, 'data'), { recursive: true })
  fs.writeFileSync(path.join(backendSource, 'app.py'), 'print("app")')
  fs.writeFileSync(path.join(backendSource, 'services', 'runtime.py'), 'RUNTIME = True')
  fs.writeFileSync(path.join(backendSource, '.venv', 'python.exe'), 'drop')
  fs.writeFileSync(path.join(backendSource, 'tests', 'test_app.py'), 'drop')
  fs.writeFileSync(path.join(backendSource, '__pycache__', 'app.pyc'), 'drop')
  fs.writeFileSync(path.join(backendSource, 'data', 'local.db'), 'drop')
  fs.writeFileSync(path.join(backendSource, 'test_port_detection.py'), 'drop')

  const result = await buildBackendRuntime({
    pythonRoot,
    sitePackages,
    backendSource,
    destination,
    port: 5409,
  })

  assert.equal(result.destination, destination)
  assert.equal(fs.readFileSync(path.join(destination, 'python', 'python.exe'), 'utf8'), 'python')
  assert.equal(
    fs.readFileSync(path.join(destination, 'python', 'Lib', 'site-packages', 'runtime_package', '__init__.py'), 'utf8'),
    'runtime = True',
  )
  assert.equal(
    fs.readFileSync(path.join(destination, 'python', 'Lib', 'site-packages', 'runtime_package-1.0.dist-info', 'LICENSE'), 'utf8'),
    'MIT',
  )
  assert.equal(fs.existsSync(path.join(destination, 'python', 'Lib', 'site-packages', 'old-package')), false)
  assert.equal(fs.existsSync(path.join(destination, 'python', 'Lib', 'site-packages', 'runtime_package', 'tests')), false)
  assert.equal(fs.existsSync(path.join(destination, 'python', 'Lib', 'site-packages', 'runtime_package', '__pycache__')), false)
  assert.equal(fs.readFileSync(path.join(destination, 'app', 'services', 'runtime.py'), 'utf8'), 'RUNTIME = True')
  assert.equal(fs.existsSync(path.join(destination, 'app', '.venv')), false)
  assert.equal(fs.existsSync(path.join(destination, 'app', 'tests')), false)
  assert.equal(fs.existsSync(path.join(destination, 'app', '__pycache__')), false)
  assert.equal(fs.existsSync(path.join(destination, 'app', 'data')), false)
  assert.equal(fs.existsSync(path.join(destination, 'app', 'test_port_detection.py')), false)
  assert.deepEqual(
    JSON.parse(fs.readFileSync(path.join(destination, 'runtime.json'), 'utf8')),
    {
      schemaVersion: 1,
      executable: 'python/python.exe',
      arguments: ['app.py'],
      workingDirectory: 'app',
      port: 5409,
    },
  )
})

test('后端运行时缺依赖或使用危险目录时拒绝且保留旧产物', async (context) => {
  const {
    buildBackendRuntime,
    validateBackendRuntimePaths,
  } = await import('../../../scripts/build-backend-runtime.mjs')
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'matrix-backend-invalid-'))
  context.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }))

  const pythonRoot = path.join(tempRoot, 'python-source')
  const sitePackages = path.join(tempRoot, 'site-packages')
  const backendSource = path.join(tempRoot, 'backend-source')
  const destination = path.join(tempRoot, 'resources', 'backend')
  fs.mkdirSync(pythonRoot, { recursive: true })
  fs.mkdirSync(sitePackages, { recursive: true })
  fs.mkdirSync(backendSource, { recursive: true })
  fs.mkdirSync(destination, { recursive: true })
  fs.writeFileSync(path.join(backendSource, 'app.py'), 'app')
  fs.writeFileSync(path.join(destination, 'keep.txt'), 'old-runtime')

  await assert.rejects(
    buildBackendRuntime({ pythonRoot, sitePackages, backendSource, destination, port: 5409 }),
    /python\.exe/,
  )
  assert.equal(fs.readFileSync(path.join(destination, 'keep.txt'), 'utf8'), 'old-runtime')

  assert.throws(
    () => validateBackendRuntimePaths({
      pythonRoot,
      sitePackages,
      backendSource,
      destination: path.join(tempRoot, 'resources', 'unsafe-runtime'),
    }),
    /暂存目录必须命名为 backend/,
  )
  assert.throws(
    () => validateBackendRuntimePaths({
      pythonRoot,
      sitePackages,
      backendSource,
      destination: path.join(backendSource, 'nested', 'backend'),
    }),
    /来源与暂存目录不能互相包含/,
  )
})
