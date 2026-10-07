import test from 'node:test'
import assert from 'node:assert/strict'
import { validateRenderStory } from '../schema.mjs'

const story = () => ({ mode: 'remotion', title: '测试', width: 1080, height: 1920, fps: 30, durationInFrames: 60, scenes: [{ title: '镜头', text: '行动', visual: 'orbit', durationInFrames: 60 }] })

test('拒绝时间轴不一致，禁止静默补时长', () => {
  assert.throws(() => validateRenderStory({ ...story(), durationInFrames: 100 }), /时间轴/)
})
test('图片引用只允许当前任务文件', () => {
  const data = story()
  data.mode = 'illustrated'
  data.scenes[0].image = '../secret.png'
  assert.throws(() => validateRenderStory(data), /图片/)
})
test('允许固定模板和准确时间轴', () => {
  assert.equal(validateRenderStory(story()).durationInFrames, 60)
})

test('配音只能引用当前镜头的 WAV 文件', () => {
  const data = story()
  data.scenes[0].audio = '../outside.wav'
  assert.throws(() => validateRenderStory(data), /配音/)
  data.scenes[0].audio = 'scene-1.wav'
  assert.equal(validateRenderStory(data).scenes[0].audio, 'scene-1.wav')
})
