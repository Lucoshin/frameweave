const SPLIT_MODES = new Set(['smartScene', 'fixedDuration'])
const SCENE_ENGINES = new Set(['content', 'adaptive'])
const FIXED_SELECTIONS = new Set([
  'automatic',
  'startOnly',
  'startAndEnd',
  'startMiddleAndEnd',
])

function requireText(value, label) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new TypeError(`${label}不能为空`)
  }

  return value
}

function requireFileList(value, label) {
  if (!Array.isArray(value) || value.length === 0) {
    throw new TypeError(`${label}不能为空`)
  }

  return value.map((item) => requireText(item, label))
}

function numberInRange(value, label, minimum, maximum) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < minimum || value > maximum) {
    throw new RangeError(`${label}必须在 ${minimum} 到 ${maximum} 之间`)
  }

  return value
}

function integerInRange(value, label, minimum, maximum) {
  numberInRange(value, label, minimum, maximum)
  if (!Number.isInteger(value)) {
    throw new TypeError(`${label}必须是整数`)
  }

  return value
}

export function buildSplitRequest(options) {
  const mode = options.mode
  if (!SPLIT_MODES.has(mode)) {
    throw new TypeError('视频分割模式无效')
  }

  let split
  if (mode === 'smartScene') {
    const sceneEngine = options.sceneEngine
    if (!SCENE_ENGINES.has(sceneEngine)) {
      throw new TypeError('场景检测模式无效')
    }

    split = {
      mode,
      sceneEngine,
      sensitivity: numberInRange(options.sensitivity, '灵敏度', 0.01, 1),
      minimumSceneDurationSeconds: numberInRange(
        options.minimumSceneDurationSeconds,
        '最短片段时长',
        0.1,
        600,
      ),
    }
  } else {
    const selection = options.selection
    if (!FIXED_SELECTIONS.has(selection)) {
      throw new TypeError('固定时长取片模式无效')
    }

    split = {
      mode,
      durationSeconds: numberInRange(options.durationSeconds, '固定片段时长', 1, 600),
      selection,
    }
  }

  return {
    schemaVersion: 1,
    operation: 'split',
    jobId: requireText(options.jobId, '任务 ID'),
    inputs: requireFileList(options.inputs, '输入视频'),
    outputDirectory: requireText(options.outputDirectory, '输出目录'),
    outputRule: 'perVideoSubfolder',
    split,
    encoding: {
      mode: 'auto',
      mute: options.mute === true,
      maxThreads: integerInRange(options.maxThreads ?? 1, '线程数', 1, 16),
    },
    subtitleRemoval: { enabled: false },
  }
}

export function buildComposeRequest(options) {
  return {
    schemaVersion: 1,
    operation: 'compose',
    jobId: requireText(options.jobId, '任务 ID'),
    clips: requireFileList(options.clips, '混剪片段'),
    outputDirectory: requireText(options.outputDirectory, '输出目录'),
    composition: {
      outputCount: integerInRange(options.outputCount, '输出视频数', 1, 100),
      clipsPerOutput: integerInRange(options.clipsPerOutput, '每条视频片段数', 1, 100),
      maxParallelism: integerInRange(options.maxParallelism, '混剪并发数', 1, 8),
      muteAudio: options.muteAudio === true,
    },
    subtitleRemoval: { enabled: false },
  }
}
