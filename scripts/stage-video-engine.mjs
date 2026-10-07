import fs from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

export const FFMPEG_LICENSE_FILES = Object.freeze([
  'FFmpeg-GPL-3.0.txt',
  'FFmpeg-Gyan-9.0.1-README.txt',
  'FFmpeg-Gyan-9.0.1-SOURCE.txt',
])

function optionValue(argv, name) {
  const index = argv.indexOf(name)
  if (index === -1) return undefined
  const value = argv[index + 1]
  if (!value || value.startsWith('--')) throw new Error(`${name} 缺少路径`)
  return value
}

async function countFiles(directory) {
  let count = 0
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    if (entry.isDirectory()) count += await countFiles(path.join(directory, entry.name))
    else if (entry.isFile()) count += 1
  }
  return count
}

export function resolveVideoEngineStage({ argv = [], env = process.env, cwd = process.cwd() } = {}) {
  const sourceValue = optionValue(argv, '--source') || env.MATRIX_VIDEO_ENGINE_SOURCE
  if (!sourceValue) {
    throw new Error('请通过 --source 或 MATRIX_VIDEO_ENGINE_SOURCE 指定视频引擎 publish 目录')
  }
  const ffmpegValue = optionValue(argv, '--ffmpeg-dir') || env.MATRIX_FFMPEG_DIR
  if (!ffmpegValue) {
    throw new Error('请通过 --ffmpeg-dir 或 MATRIX_FFMPEG_DIR 指定 FFmpeg 目录')
  }
  const licenseValue = optionValue(argv, '--license-dir') || env.MATRIX_FFMPEG_LICENSE_DIR
  if (!licenseValue) {
    throw new Error('请通过 --license-dir 或 MATRIX_FFMPEG_LICENSE_DIR 指定 FFmpeg 许可证目录')
  }
  return {
    source: path.resolve(cwd, sourceValue),
    destination: path.resolve(
      cwd,
      optionValue(argv, '--destination') || path.join('build-resources', 'video-engine'),
    ),
    ffmpegDir: path.resolve(cwd, ffmpegValue),
    licenseDir: path.resolve(cwd, licenseValue),
  }
}

function isInside(parent, candidate) {
  const relation = path.relative(parent, candidate)
  return relation.length > 0 && !relation.startsWith(`..${path.sep}`) && relation !== '..' && !path.isAbsolute(relation)
}

export function validateVideoEngineStagePaths({ source, destination, ffmpegDir, licenseDir }) {
  const resolved = {
    source: path.resolve(source),
    destination: path.resolve(destination),
    ffmpegDir: path.resolve(ffmpegDir),
    licenseDir: path.resolve(licenseDir),
  }
  if (path.basename(resolved.destination).toLowerCase() !== 'video-engine') {
    throw new Error('视频引擎暂存目录必须命名为 video-engine')
  }
  for (const input of [resolved.source, resolved.ffmpegDir, resolved.licenseDir]) {
    if (
      input === resolved.destination
      || isInside(input, resolved.destination)
      || isInside(resolved.destination, input)
    ) {
      throw new Error('视频引擎来源与暂存目录不能互相包含')
    }
  }
  return resolved
}

async function requireFile(filePath, errorMessage) {
  const stats = await fs.stat(filePath).catch(() => null)
  if (!stats?.isFile()) throw new Error(`${errorMessage}：${filePath}`)
}

async function replaceDirectory(staging, destination) {
  const backup = path.join(
    path.dirname(destination),
    `.video-engine-backup-${process.pid}-${Date.now()}`,
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
      await fs.rm(destination, { recursive: true, force: true })
      await fs.rename(backup, destination)
      oldMoved = false
    }
    throw error
  } finally {
    if (oldMoved) await fs.rm(backup, { recursive: true, force: true })
  }
}

export async function stageVideoEngine({ source, destination, ffmpegDir, licenseDir }) {
  const {
    source: resolvedSource,
    destination: resolvedDestination,
    ffmpegDir: resolvedFfmpegDir,
    licenseDir: resolvedLicenseDir,
  } = validateVideoEngineStagePaths({ source, destination, ffmpegDir, licenseDir })

  const sourceStats = await fs.stat(resolvedSource).catch(() => null)
  if (!sourceStats?.isDirectory()) throw new Error(`视频引擎 publish 目录不存在：${resolvedSource}`)
  const executable = path.join(resolvedSource, 'MaterialHarvester.Cli.exe')
  await requireFile(executable, 'publish 目录缺少 MaterialHarvester.Cli.exe')
  for (const executableName of ['ffmpeg.exe', 'ffprobe.exe']) {
    await requireFile(
      path.join(resolvedFfmpegDir, executableName),
      `FFmpeg 目录缺少 ${executableName}`,
    )
  }
  for (const licenseName of FFMPEG_LICENSE_FILES) {
    await requireFile(
      path.join(resolvedLicenseDir, licenseName),
      `FFmpeg 许可证目录缺少 ${licenseName}`,
    )
  }

  const parent = path.dirname(resolvedDestination)
  const staging = path.join(parent, `.video-engine-staging-${process.pid}-${Date.now()}`)
  await fs.mkdir(parent, { recursive: true })
  try {
    await fs.cp(resolvedSource, staging, { recursive: true, errorOnExist: true })
    for (const executableName of ['ffmpeg.exe', 'ffprobe.exe']) {
      await fs.copyFile(
        path.join(resolvedFfmpegDir, executableName),
        path.join(staging, executableName),
      )
    }
    const stagedLicenses = path.join(staging, 'licenses')
    await fs.mkdir(stagedLicenses, { recursive: true })
    for (const licenseName of FFMPEG_LICENSE_FILES) {
      await fs.copyFile(
        path.join(resolvedLicenseDir, licenseName),
        path.join(stagedLicenses, licenseName),
      )
    }
    const fileCount = await countFiles(staging)
    await replaceDirectory(staging, resolvedDestination)
    return { destination: resolvedDestination, fileCount }
  } finally {
    await fs.rm(staging, { recursive: true, force: true })
  }
}

async function main() {
  const options = resolveVideoEngineStage({ argv: process.argv.slice(2) })
  const result = await stageVideoEngine(options)
  console.log(`视频引擎已暂存：${result.destination}（${result.fileCount} 个文件）`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(error.message)
    process.exitCode = 1
  })
}
