import assert from 'node:assert/strict'
import test from 'node:test'

import { buildSplitRequest, buildComposeRequest } from '../shared/video-engine-contract.js'

test('智能分割请求固定版本并强制关闭去字幕', () => {
  const request = buildSplitRequest({
    jobId: 'job-001',
    inputs: ['D:\\素材\\原片 01.mp4'],
    outputDirectory: 'D:\\输出',
    mode: 'smartScene',
    sceneEngine: 'adaptive',
    sensitivity: 0.72,
    minimumSceneDurationSeconds: 3,
    maxThreads: 4,
    mute: false,
  })

  assert.deepEqual(request, {
    schemaVersion: 1,
    operation: 'split',
    jobId: 'job-001',
    inputs: ['D:\\素材\\原片 01.mp4'],
    outputDirectory: 'D:\\输出',
    outputRule: 'perVideoSubfolder',
    split: {
      mode: 'smartScene',
      sceneEngine: 'adaptive',
      sensitivity: 0.72,
      minimumSceneDurationSeconds: 3,
    },
    encoding: { mode: 'auto', mute: false, maxThreads: 4 },
    subtitleRemoval: { enabled: false },
  })
})

test('固定时长只接受已确认的取片模式', () => {
  assert.throws(
    () => buildSplitRequest({
      jobId: 'job-002',
      inputs: ['a.mp4'],
      outputDirectory: 'out',
      mode: 'fixedDuration',
      durationSeconds: 10,
      selection: 'unknown',
    }),
    /固定时长取片模式无效/,
  )
})

test('混剪请求限制输出数、每条片段数和并发数', () => {
  const request = buildComposeRequest({
    jobId: 'job-003',
    clips: ['a.mp4', 'b.mp4', 'c.mp4'],
    outputDirectory: 'out',
    outputCount: 2,
    clipsPerOutput: 3,
    maxParallelism: 2,
    muteAudio: true,
  })

  assert.equal(request.operation, 'compose')
  assert.equal(request.schemaVersion, 1)
  assert.deepEqual(request.composition, {
    outputCount: 2,
    clipsPerOutput: 3,
    maxParallelism: 2,
    muteAudio: true,
  })
  assert.deepEqual(request.subtitleRemoval, { enabled: false })
})
