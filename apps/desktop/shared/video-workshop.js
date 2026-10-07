import { buildComposeRequest, buildSplitRequest } from './video-engine-contract.js'

export function createSplitJob(options) {
  return buildSplitRequest(options)
}

export function createComposeJob(options) {
  return buildComposeRequest(options)
}

export function createVideoJobId(operation, now = Date.now, random = Math.random) {
  const timestamp = now().toString(36)
  const entropy = Math.floor(random() * 0x1000000).toString(36).padStart(5, '0')
  return `${operation}-${timestamp}-${entropy}`
}
