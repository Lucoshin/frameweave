import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { StringDecoder } from 'node:string_decoder'
import { setTimeout as wait } from 'node:timers/promises'

const VIDEO_ENGINE_OPERATIONS = new Set(['split', 'compose'])

function requireAbsolutePath(value, label) {
  if (typeof value !== 'string' || !path.isAbsolute(value)) {
    throw new TypeError(`${label}必须是绝对路径`)
  }
  return value
}

function createEventPump(eventsPath, onEvent, pollIntervalMs) {
  const decoder = new StringDecoder('utf8')
  let byteOffset = 0
  let remainder = ''
  let stopped = false

  async function drain(final = false) {
    const content = await readFile(eventsPath)
    if (content.length > byteOffset) {
      remainder += decoder.write(content.subarray(byteOffset))
      byteOffset = content.length
    }
    if (final) remainder += decoder.end()

    const lines = remainder.split(/\r?\n/)
    remainder = final ? '' : lines.pop()
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line))
    }
    if (final && remainder.trim()) onEvent(JSON.parse(remainder))
  }

  const completed = (async () => {
    while (!stopped) {
      await drain()
      await wait(pollIntervalMs)
    }
    await drain(true)
  })()

  return {
    completed,
    stop() {
      stopped = true
    },
  }
}

function waitForProcess(child) {
  return new Promise((resolve, reject) => {
    let stderr = ''
    child.stderr?.setEncoding('utf8')
    child.stderr?.on('data', (chunk) => { stderr += chunk })
    child.once('error', reject)
    child.once('close', (code, signal) => resolve({ code, signal, stderr }))
  })
}

export function createVideoEngineRunner({
  executablePath,
  executableArguments = [],
  jobRoot,
  eventPollIntervalMs = 25,
}) {
  const configuredExecutablePath = requireAbsolutePath(executablePath, '视频引擎路径')
  const configuredJobRoot = requireAbsolutePath(jobRoot, '视频任务目录')
  if (!Array.isArray(executableArguments) || executableArguments.some((item) => typeof item !== 'string')) {
    throw new TypeError('视频引擎固定参数必须是字符串数组')
  }
  if (!Number.isInteger(eventPollIntervalMs) || eventPollIntervalMs < 1) {
    throw new RangeError('事件轮询间隔必须是正整数')
  }
  const configuredArguments = [...executableArguments]

  return {
    async start(request, { onEvent = () => {} } = {}) {
      if (!request || !VIDEO_ENGINE_OPERATIONS.has(request.operation)) {
        throw new TypeError('视频引擎 runner 只接受 split 或 compose 请求')
      }
      if (typeof onEvent !== 'function') {
        throw new TypeError('onEvent 必须是函数')
      }

      await mkdir(configuredJobRoot, { recursive: true })
      const jobDirectory = await mkdtemp(path.join(configuredJobRoot, 'job-'))
      const requestPath = path.join(jobDirectory, 'request.json')
      const eventsPath = path.join(jobDirectory, 'events.jsonl')
      const resultPath = path.join(jobDirectory, 'result.json')
      const cancelPath = path.join(jobDirectory, 'cancel.signal')

      await writeFile(requestPath, JSON.stringify(request), 'utf8')
      await writeFile(eventsPath, '', 'utf8')

      const eventPump = createEventPump(eventsPath, onEvent, eventPollIntervalMs)
      const child = spawn(configuredExecutablePath, [
        ...configuredArguments,
        request.operation,
        '--request', requestPath,
        '--events', eventsPath,
        '--result', resultPath,
        '--cancel', cancelPath,
      ], {
        shell: false,
        windowsHide: true,
        stdio: ['ignore', 'ignore', 'pipe'],
      })

      const completed = (async () => {
        let outcome
        let processError
        try {
          outcome = await waitForProcess(child)
        } catch (error) {
          processError = error
        } finally {
          eventPump.stop()
        }

        await eventPump.completed
        if (processError) throw processError

        let result
        try {
          result = JSON.parse(await readFile(resultPath, 'utf8'))
          if (!result || typeof result !== 'object' || Array.isArray(result) || typeof result.status !== 'string') {
            throw new TypeError('视频引擎结果必须是带 status 的对象')
          }
        } catch (error) {
          const details = outcome.stderr.trim()
          throw new Error(`视频引擎没有生成有效结果${details ? `：${details}` : ''}`, { cause: error })
        }

        return result
      })()

      let cancelRequested = false
      return {
        completed,
        async cancel() {
          if (cancelRequested) return
          cancelRequested = true
          // 让 C# 引擎自行取消 CancellationToken，才能连同 FFmpeg 子进程和半成品一起收尾。
          await writeFile(cancelPath, 'cancel\n', { encoding: 'utf8', flag: 'wx' })
        },
      }
    },
  }
}
