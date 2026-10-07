import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

const packageJson = JSON.parse(fs.readFileSync(new URL('../../../package.json', import.meta.url), 'utf8'))

test('electron-builder 生成可选择安装目录的 x64 NSIS 安装包', () => {
  assert.equal(packageJson.devDependencies['electron-builder'].startsWith('^'), true)
  assert.equal(packageJson.build.appId, 'cn.matrixstudio.desktop')
  assert.equal(packageJson.build.asar, true)
  assert.deepEqual(packageJson.build.win.target, [{ target: 'nsis', arch: ['x64'] }])
  assert.equal(packageJson.build.nsis.oneClick, false)
  assert.equal(packageJson.build.nsis.perMachine, false)
  assert.equal(packageJson.build.nsis.allowToChangeInstallationDirectory, true)
})

test('打包仅携带生产界面、桌面代码与暂存后的运行时', () => {
  assert.equal(packageJson.build.files.includes('apps/desktop/**/*'), true)
  assert.equal(
    packageJson.build.files.includes('vendor/social-auto-upload-web-ui/frontend/dist/**/*'),
    true,
  )
  assert.equal(packageJson.build.files.includes('THIRD_PARTY_NOTICES.md'), true)
  assert.equal(packageJson.build.files.includes('vendor/social-auto-upload-web-ui/LICENSE'), true)
  assert.equal(
    packageJson.build.extraResources.some((item) => item.to === 'video-engine'),
    true,
  )
  assert.equal(
    packageJson.build.extraResources.some((item) => item.to === 'backend'),
    true,
  )
  assert.equal(
    packageJson.build.extraResources.some((item) => (
      item.from === 'THIRD_PARTY_NOTICES.md'
      && item.to === 'THIRD_PARTY_NOTICES.md'
    )),
    true,
  )
  assert.equal(
    packageJson.build.extraResources.some((item) => (
      item.from === 'vendor/social-auto-upload-web-ui/LICENSE'
      && item.to === 'licenses/social-auto-upload-web-ui-LICENSE'
    )),
    true,
  )
  assert.equal(
    packageJson.scripts['build:backend-runtime'],
    'node scripts/build-backend-runtime.mjs',
  )
  assert.equal('docxtemplater' in packageJson.dependencies, true)
  assert.equal('pizzip' in packageJson.dependencies, true)
})

test('视频引擎暂存脚本携带 FFmpeg 二进制和对应许可证材料', async (context) => {
  const {
    resolveVideoEngineStage,
    stageVideoEngine,
    validateVideoEngineStagePaths,
  } = await import('../../../scripts/stage-video-engine.mjs')
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'matrix-video-stage-'))
  context.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }))
  const source = path.join(tempRoot, 'publish')
  const ffmpegDir = path.join(tempRoot, 'ffmpeg')
  const licenseDir = path.join(tempRoot, 'licenses')
  const destination = path.join(tempRoot, 'resources', 'video-engine')
  fs.mkdirSync(source, { recursive: true })
  fs.mkdirSync(ffmpegDir, { recursive: true })
  fs.mkdirSync(licenseDir, { recursive: true })
  fs.writeFileSync(path.join(source, 'MaterialHarvester.Cli.exe'), 'exe')
  fs.writeFileSync(path.join(source, 'MaterialHarvester.Core.dll'), 'dll')
  fs.writeFileSync(path.join(ffmpegDir, 'ffmpeg.exe'), 'ffmpeg')
  fs.writeFileSync(path.join(ffmpegDir, 'ffprobe.exe'), 'ffprobe')
  for (const name of [
    'FFmpeg-GPL-3.0.txt',
    'FFmpeg-Gyan-9.0.1-README.txt',
    'FFmpeg-Gyan-9.0.1-SOURCE.txt',
  ]) {
    fs.writeFileSync(path.join(licenseDir, name), name)
  }

  const result = await stageVideoEngine({ source, destination, ffmpegDir, licenseDir })

  assert.equal(result.fileCount, 7)
  assert.equal(fs.readFileSync(path.join(destination, 'MaterialHarvester.Cli.exe'), 'utf8'), 'exe')
  assert.equal(fs.readFileSync(path.join(destination, 'MaterialHarvester.Core.dll'), 'utf8'), 'dll')
  assert.equal(fs.readFileSync(path.join(destination, 'ffmpeg.exe'), 'utf8'), 'ffmpeg')
  assert.equal(fs.readFileSync(path.join(destination, 'ffprobe.exe'), 'utf8'), 'ffprobe')
  assert.equal(
    fs.readFileSync(path.join(destination, 'licenses', 'FFmpeg-GPL-3.0.txt'), 'utf8'),
    'FFmpeg-GPL-3.0.txt',
  )
  assert.deepEqual(
    resolveVideoEngineStage({
      argv: ['--source', source, '--ffmpeg-dir', ffmpegDir, '--license-dir', licenseDir],
      env: {},
      cwd: tempRoot,
    }),
    { source, destination: path.join(tempRoot, 'build-resources', 'video-engine'), ffmpegDir, licenseDir },
  )

  const invalidSource = path.join(tempRoot, 'invalid')
  fs.mkdirSync(invalidSource)
  await assert.rejects(
    stageVideoEngine({ source: invalidSource, destination, ffmpegDir, licenseDir }),
    /MaterialHarvester\.Cli\.exe/,
  )
  await assert.rejects(
    stageVideoEngine({ source, destination: path.join(tempRoot, 'resources', 'unsafe-runtime'), ffmpegDir, licenseDir }),
    /暂存目录必须命名为 video-engine/,
  )
  assert.throws(
    () => validateVideoEngineStagePaths({
      source,
      ffmpegDir,
      licenseDir,
      destination: path.join(source, 'nested', 'video-engine'),
    }),
    /来源与暂存目录不能互相包含/,
  )
})

test('视频引擎缺任一 FFmpeg 依赖或许可证时拒绝且不覆盖旧产物', async (context) => {
  const { stageVideoEngine } = await import('../../../scripts/stage-video-engine.mjs')
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'matrix-video-invalid-'))
  context.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }))
  const source = path.join(tempRoot, 'publish')
  const ffmpegDir = path.join(tempRoot, 'ffmpeg')
  const licenseDir = path.join(tempRoot, 'licenses')
  const destination = path.join(tempRoot, 'resources', 'video-engine')
  fs.mkdirSync(source, { recursive: true })
  fs.mkdirSync(ffmpegDir, { recursive: true })
  fs.mkdirSync(licenseDir, { recursive: true })
  fs.mkdirSync(destination, { recursive: true })
  fs.writeFileSync(path.join(source, 'MaterialHarvester.Cli.exe'), 'exe')
  fs.writeFileSync(path.join(ffmpegDir, 'ffmpeg.exe'), 'ffmpeg')
  fs.writeFileSync(path.join(destination, 'keep.txt'), 'old-runtime')
  for (const name of [
    'FFmpeg-GPL-3.0.txt',
    'FFmpeg-Gyan-9.0.1-README.txt',
    'FFmpeg-Gyan-9.0.1-SOURCE.txt',
  ]) {
    fs.writeFileSync(path.join(licenseDir, name), name)
  }

  await assert.rejects(
    stageVideoEngine({ source, destination, ffmpegDir, licenseDir }),
    /ffprobe\.exe/,
  )
  assert.equal(fs.readFileSync(path.join(destination, 'keep.txt'), 'utf8'), 'old-runtime')

  fs.writeFileSync(path.join(ffmpegDir, 'ffprobe.exe'), 'ffprobe')
  fs.rmSync(path.join(licenseDir, 'FFmpeg-Gyan-9.0.1-SOURCE.txt'))
  await assert.rejects(
    stageVideoEngine({ source, destination, ffmpegDir, licenseDir }),
    /FFmpeg-Gyan-9\.0\.1-SOURCE\.txt/,
  )
  assert.equal(fs.readFileSync(path.join(destination, 'keep.txt'), 'utf8'), 'old-runtime')
})

test('视频引擎构建参数仅来自命令行或 MATRIX_VIDEO_ENGINE_PROJECT', async () => {
  const {
    createDotnetPublishSpec,
    resolveVideoEngineBuild,
  } = await import('../../../scripts/build-video-engine.mjs')
  const cwd = path.resolve('D:\\MatrixWorkspace')
  const project = path.resolve('D:\\VideoEngine\\MaterialHarvester.Cli\\MaterialHarvester.Cli.csproj')
  const ffmpegDir = path.resolve('D:\\Prepared\\ffmpeg')

  assert.deepEqual(
    resolveVideoEngineBuild({
      argv: [],
      env: {
        MATRIX_VIDEO_ENGINE_PROJECT: project,
        MATRIX_FFMPEG_DIR: ffmpegDir,
      },
      cwd,
    }),
    {
      project,
      output: path.join(cwd, 'build-resources', 'video-engine'),
      configuration: 'Release',
      runtime: 'win-x64',
      selfContained: true,
      ffmpegDir,
      licenseDir: path.resolve(path.dirname(project), '..', 'packaging', 'licenses'),
    },
  )
  assert.throws(
    () => resolveVideoEngineBuild({ argv: [], env: {}, cwd }),
    /--project 或 MATRIX_VIDEO_ENGINE_PROJECT/,
  )
  assert.throws(
    () => resolveVideoEngineBuild({
      argv: ['--project', project],
      env: {},
      cwd,
    }),
    /--ffmpeg-dir 或 MATRIX_FFMPEG_DIR/,
  )

  const spec = createDotnetPublishSpec({
    project,
    configuration: 'Release',
    runtime: 'win-x64',
    selfContained: true,
    temporaryOutput: path.resolve('D:\\Prepared\\video-publish'),
  })
  assert.equal(spec.command, 'dotnet')
  assert.deepEqual(
    spec.arguments.slice(spec.arguments.indexOf('--self-contained'), spec.arguments.indexOf('--self-contained') + 2),
    ['--self-contained', 'true'],
  )
  assert.equal(spec.arguments.some((item) => /PublishSingleFile/i.test(item)), false)
})

test('桌面界面构建使用相对资源路径并固定本机 API 地址', async () => {
  const { createDesktopUiBuildSpec } = await import('../../../scripts/build-desktop-ui.mjs')
  const spec = createDesktopUiBuildSpec({
    nodeExecutable: 'C:\\Node\\node.exe',
    env: { PATH: 'demo', npm_execpath: 'C:\\Node\\npm-cli.js' },
    cwd: path.resolve('D:\\MatrixWorkspace'),
    buildId: 'test-build',
  })
  const frontendDirectory = path.resolve(
    'D:\\MatrixWorkspace',
    'vendor',
    'social-auto-upload-web-ui',
    'frontend',
  )

  assert.equal(spec.command, 'C:\\Node\\node.exe')
  assert.deepEqual(spec.arguments, [
    'C:\\Node\\npm-cli.js',
    '--prefix',
    'vendor/social-auto-upload-web-ui/frontend',
    'run',
    'build',
    '--',
    '--base=./',
    '--outDir',
    path.join(frontendDirectory, '.matrix-dist-test-build'),
    '--emptyOutDir',
  ])
  assert.equal(spec.outputDirectory, path.join(frontendDirectory, 'dist'))
  assert.equal(spec.stagingDirectory, path.join(frontendDirectory, '.matrix-dist-test-build'))
  assert.equal(spec.environment.VITE_API_BASE_URL, 'http://127.0.0.1:5409')
  assert.equal(spec.environment.PATH, 'demo')
})

test('桌面界面从干净临时目录原子替换 dist 且不会保留旧哈希资源', async (context) => {
  const { replaceDesktopUiOutput } = await import('../../../scripts/build-desktop-ui.mjs')
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'matrix-ui-output-'))
  context.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }))
  const outputDirectory = path.join(tempRoot, 'dist')
  const stagingDirectory = path.join(tempRoot, '.matrix-dist-test')
  fs.mkdirSync(path.join(outputDirectory, 'assets'), { recursive: true })
  fs.mkdirSync(path.join(stagingDirectory, 'assets'), { recursive: true })
  fs.writeFileSync(path.join(outputDirectory, 'assets', 'VideoWorkshop-old.js'), 'old')
  fs.writeFileSync(path.join(stagingDirectory, 'index.html'), 'new-index')
  fs.writeFileSync(path.join(stagingDirectory, 'assets', 'VideoWorkshop-new.js'), 'new')

  await replaceDesktopUiOutput({ outputDirectory, stagingDirectory })

  assert.equal(fs.existsSync(path.join(outputDirectory, 'assets', 'VideoWorkshop-old.js')), false)
  assert.equal(
    fs.readFileSync(path.join(outputDirectory, 'assets', 'VideoWorkshop-new.js'), 'utf8'),
    'new',
  )
  assert.equal(fs.readFileSync(path.join(outputDirectory, 'index.html'), 'utf8'), 'new-index')
  assert.equal(fs.existsSync(stagingDirectory), false)
})
