import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { promisify } from 'node:util'

import { createVideoEngineRunner } from '../electron/video-engine-runner.js'
import { createComposeJob, createSplitJob } from '../shared/video-workshop.js'

const execFileAsync = promisify(execFile)
const enginePath = process.env.MATRIX_VIDEO_ENGINE_REAL_TEST
const ffmpegPath = process.env.MATRIX_FFMPEG_REAL_TEST

test('真实视频引擎完成 runner → C# → FFmpeg 分割与混剪', {
  skip: !enginePath || !ffmpegPath,
  timeout: 120_000,
}, async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'matrix-real-video-'))
  try {
    const inputPath = path.join(root, '样例 原片.mp4')
    await execFileAsync(ffmpegPath, [
      '-hide_banner', '-loglevel', 'error', '-y',
      '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=24',
      '-t', '4', '-c:v', 'mpeg4', '-q:v', '5', inputPath,
    ])

    const runner = createVideoEngineRunner({
      executablePath: enginePath,
      jobRoot: path.join(root, 'jobs'),
      eventPollIntervalMs: 10,
    })
    const splitTask = await runner.start(createSplitJob({
      jobId: 'real-split',
      inputs: [inputPath],
      outputDirectory: path.join(root, 'split'),
      mode: 'fixedDuration',
      durationSeconds: 2,
      selection: 'automatic',
      mute: true,
      maxThreads: 1,
    }))
    const splitResult = await splitTask.completed
    assert.equal(splitResult.status, 'succeeded')
    const clips = splitResult.items.flatMap(item => item.outputs)
    assert.equal(clips.length, 2)

    const composeTask = await runner.start(createComposeJob({
      jobId: 'real-compose',
      clips,
      outputDirectory: path.join(root, 'compose'),
      outputCount: 1,
      clipsPerOutput: 2,
      maxParallelism: 1,
      muteAudio: true,
    }))
    const composeResult = await composeTask.completed
    assert.equal(composeResult.status, 'succeeded')
    assert.equal(composeResult.items.flatMap(item => item.outputs).length, 1)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
