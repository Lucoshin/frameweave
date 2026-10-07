import fs from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const RUNTIME_MANIFEST = Object.freeze({
  schemaVersion: 1,
  executable: 'python/python.exe',
  arguments: ['app.py'],
  workingDirectory: 'app',
})

// Windows Defender / 索引服务可能在大目录复制后短暂占用文件句柄。
// Node 的 fs.rm 只有显式设置 maxRetries 时才会重试 EBUSY/EPERM。
export const REMOVE_TREE_OPTIONS = Object.freeze({
  recursive: true,
  force: true,
  maxRetries: 5,
  retryDelay: 200,
})

function removeTree(target) {
  return fs.rm(target, REMOVE_TREE_OPTIONS)
}

function optionValue(argv, name) {
  const index = argv.indexOf(name)
  if (index === -1) return undefined
  const value = argv[index + 1]
  if (!value || value.startsWith('--')) throw new Error(`${name} 缺少值`)
  return value
}

function requiredSource(argv, env, optionName, environmentName) {
  const value = optionValue(argv, optionName) || env[environmentName]
  if (!value) throw new Error(`请通过 ${optionName} 或 ${environmentName} 指定来源目录`)
  return value
}

function parsePort(value) {
  const port = Number(value ?? 5409)
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error('后端端口必须是 1024-65535 的整数')
  }
  return port
}

export function resolveBackendRuntimeBuild({ argv = [], env = process.env, cwd = process.cwd() } = {}) {
  return {
    pythonRoot: path.resolve(cwd, requiredSource(argv, env, '--python-root', 'MATRIX_PYTHON_ROOT')),
    sitePackages: path.resolve(
      cwd,
      requiredSource(argv, env, '--site-packages', 'MATRIX_PYTHON_SITE_PACKAGES'),
    ),
    backendSource: path.resolve(
      cwd,
      requiredSource(argv, env, '--backend-source', 'MATRIX_BACKEND_SOURCE'),
    ),
    destination: path.resolve(
      cwd,
      optionValue(argv, '--destination') || path.join('build-resources', 'backend'),
    ),
    port: parsePort(optionValue(argv, '--port') || env.MATRIX_BACKEND_PORT),
  }
}

function isInside(parent, candidate) {
  const relation = path.relative(parent, candidate)
  return relation.length > 0
    && !relation.startsWith(`..${path.sep}`)
    && relation !== '..'
    && !path.isAbsolute(relation)
}

export function validateBackendRuntimePaths({ pythonRoot, sitePackages, backendSource, destination }) {
  const resolved = {
    pythonRoot: path.resolve(pythonRoot),
    sitePackages: path.resolve(sitePackages),
    backendSource: path.resolve(backendSource),
    destination: path.resolve(destination),
  }
  if (path.basename(resolved.destination).toLowerCase() !== 'backend') {
    throw new Error('Python 后端暂存目录必须命名为 backend')
  }
  for (const source of [resolved.pythonRoot, resolved.sitePackages, resolved.backendSource]) {
    if (
      source === resolved.destination
      || isInside(source, resolved.destination)
      || isInside(resolved.destination, source)
    ) {
      throw new Error('Python 后端来源与暂存目录不能互相包含')
    }
  }
  return resolved
}

async function requireDirectory(directory, label) {
  const stats = await fs.stat(directory).catch(() => null)
  if (!stats?.isDirectory()) throw new Error(`${label}不存在：${directory}`)
}

async function requireFile(filePath, label) {
  const stats = await fs.stat(filePath).catch(() => null)
  if (!stats?.isFile()) throw new Error(`${label}不存在：${filePath}`)
}

function segmentsFrom(root, source) {
  const relative = path.relative(root, source)
  return relative ? relative.split(path.sep) : []
}

function excludesCache(segments) {
  const names = segments.map((item) => item.toLowerCase())
  return names.some((item) => [
    '__pycache__',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '.git',
  ].includes(item))
}

function includePythonRuntime(root, source) {
  const segments = segmentsFrom(root, source)
  if (excludesCache(segments) || segments.some((item) => item.toLowerCase() === '.venv')) return false
  const normalized = segments.map((item) => item.toLowerCase())
  return !(normalized[0] === 'lib' && normalized[1] === 'site-packages')
}

function includeSitePackage(root, source) {
  const segments = segmentsFrom(root, source)
  if (excludesCache(segments)) return false
  return !segments.some((item) => ['test', 'tests'].includes(item.toLowerCase()))
}

function includeBackendSource(root, source) {
  const segments = segmentsFrom(root, source)
  if (excludesCache(segments)) return false
  if (segments.length > 0 && ['.venv', 'tests', 'data'].includes(segments[0].toLowerCase())) {
    return false
  }
  return !(segments.length === 1 && /^test(?:_|$).*\.py$/i.test(segments[0]))
}

async function countFiles(directory) {
  let count = 0
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    if (entry.isDirectory()) count += await countFiles(path.join(directory, entry.name))
    else if (entry.isFile()) count += 1
  }
  return count
}

async function replaceDirectory(staging, destination) {
  const backup = path.join(
    path.dirname(destination),
    `.backend-backup-${process.pid}-${Date.now()}`,
  )
  const destinationExists = Boolean(await fs.stat(destination).catch(() => null))
  let oldMoved = false
  try {
    if (destinationExists) {
      await fs.rename(destination, backup)
      oldMoved = true
    }
    await fs.rename(staging, destination)
  } catch (error) {
    if (oldMoved) {
      await removeTree(destination)
      await fs.rename(backup, destination)
      oldMoved = false
    }
    throw error
  } finally {
    if (oldMoved) await removeTree(backup)
  }
}

export async function buildBackendRuntime(options) {
  const {
    pythonRoot,
    sitePackages,
    backendSource,
    destination,
  } = validateBackendRuntimePaths(options)
  const port = parsePort(options.port)

  await requireDirectory(pythonRoot, 'Python portable 目录')
  await requireDirectory(sitePackages, 'Python site-packages 目录')
  await requireDirectory(backendSource, 'Python 后端源码目录')
  await requireFile(path.join(pythonRoot, 'python.exe'), 'Python portable 的 python.exe')
  await requireFile(path.join(backendSource, 'app.py'), 'Python 后端入口 app.py')

  const parent = path.dirname(destination)
  const staging = path.join(parent, `.backend-staging-${process.pid}-${Date.now()}`)
  await fs.mkdir(parent, { recursive: true })
  let operationError = null
  try {
    const stagedPython = path.join(staging, 'python')
    const stagedSitePackages = path.join(stagedPython, 'Lib', 'site-packages')
    const stagedApp = path.join(staging, 'app')
    await fs.cp(pythonRoot, stagedPython, {
      recursive: true,
      errorOnExist: true,
      filter: (source) => includePythonRuntime(pythonRoot, source),
    })
    await fs.mkdir(path.dirname(stagedSitePackages), { recursive: true })
    await fs.cp(sitePackages, stagedSitePackages, {
      recursive: true,
      errorOnExist: true,
      filter: (source) => includeSitePackage(sitePackages, source),
    })
    await fs.cp(backendSource, stagedApp, {
      recursive: true,
      errorOnExist: true,
      filter: (source) => includeBackendSource(backendSource, source),
    })
    await fs.writeFile(
      path.join(staging, 'runtime.json'),
      `${JSON.stringify({ ...RUNTIME_MANIFEST, port }, null, 2)}\n`,
      'utf8',
    )
    const fileCount = await countFiles(staging)
    await replaceDirectory(staging, destination)
    return { destination, fileCount }
  } catch (error) {
    operationError = error
    throw error
  } finally {
    try {
      await removeTree(staging)
    } catch (cleanupError) {
      // 清理失败不能覆盖复制/替换阶段的原始错误，否则会丢失真正根因。
      if (!operationError) throw cleanupError
      operationError.cleanupError = cleanupError
    }
  }
}

async function main() {
  const options = resolveBackendRuntimeBuild({ argv: process.argv.slice(2) })
  const result = await buildBackendRuntime(options)
  console.log(`Python 后端运行时已构建：${result.destination}（${result.fileCount} 个文件）`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(error.message)
    process.exitCode = 1
  })
}
