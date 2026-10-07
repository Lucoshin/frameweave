import { spawn } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

import { stageVideoEngine } from './stage-video-engine.mjs'

function optionValue(argv, name) {
  const index = argv.indexOf(name)
  if (index === -1) return undefined
  const value = argv[index + 1]
  if (!value || value.startsWith('--')) throw new Error(`${name} 缺少值`)
  return value
}

export function resolveVideoEngineBuild({ argv = [], env = process.env, cwd = process.cwd() } = {}) {
  const projectValue = optionValue(argv, '--project') || env.MATRIX_VIDEO_ENGINE_PROJECT
  if (!projectValue) {
    throw new Error('请通过 --project 或 MATRIX_VIDEO_ENGINE_PROJECT 指定 MaterialHarvester.Cli.csproj')
  }
  const ffmpegValue = optionValue(argv, '--ffmpeg-dir') || env.MATRIX_FFMPEG_DIR
  if (!ffmpegValue) {
    throw new Error('请通过 --ffmpeg-dir 或 MATRIX_FFMPEG_DIR 指定 FFmpeg 目录')
  }
  const project = path.resolve(cwd, projectValue)
  const explicitLicenseValue = optionValue(argv, '--license-dir') || env.MATRIX_FFMPEG_LICENSE_DIR
  if (!explicitLicenseValue && path.basename(path.dirname(project)).toLowerCase() !== 'materialharvester.cli') {
    throw new Error('无法从 CLI 工程结构确认许可证目录，请通过 --license-dir 或 MATRIX_FFMPEG_LICENSE_DIR 显式指定')
  }
  return {
    project,
    output: path.resolve(cwd, optionValue(argv, '--output') || path.join('build-resources', 'video-engine')),
    configuration: optionValue(argv, '--configuration') || 'Release',
    runtime: optionValue(argv, '--runtime') || 'win-x64',
    selfContained: true,
    ffmpegDir: path.resolve(cwd, ffmpegValue),
    licenseDir: explicitLicenseValue
      ? path.resolve(cwd, explicitLicenseValue)
      : path.resolve(path.dirname(project), '..', 'packaging', 'licenses'),
  }
}

export function createDotnetPublishSpec({
  project,
  configuration,
  runtime,
  selfContained,
  temporaryOutput,
}) {
  return {
    command: 'dotnet',
    arguments: [
      'publish',
      project,
      '--configuration', configuration,
      '--runtime', runtime,
      '--self-contained', String(selfContained),
      '--output', temporaryOutput,
    ],
  }
}

function run(command, argumentsList, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, argumentsList, options)
    child.once('error', reject)
    child.once('exit', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`dotnet publish 失败，退出码 ${code}`))
    })
  })
}

export async function buildVideoEngine(options) {
  const temporaryOutput = path.join(
    path.dirname(options.output),
    `.video-engine-publish-${process.pid}-${Date.now()}`,
  )
  await fs.mkdir(path.dirname(options.output), { recursive: true })
  try {
    const publish = createDotnetPublishSpec({ ...options, temporaryOutput })
    await run(publish.command, publish.arguments, { stdio: 'inherit', windowsHide: true })
    return await stageVideoEngine({
      source: temporaryOutput,
      destination: options.output,
      ffmpegDir: options.ffmpegDir,
      licenseDir: options.licenseDir,
    })
  } finally {
    await fs.rm(temporaryOutput, { recursive: true, force: true })
  }
}

async function main() {
  const options = resolveVideoEngineBuild({ argv: process.argv.slice(2) })
  const result = await buildVideoEngine(options)
  console.log(`视频引擎构建完成：${result.destination}（${result.fileCount} 个文件）`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(error.message)
    process.exitCode = 1
  })
}
