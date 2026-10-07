export function validateRenderStory(story) {
  if (!story || !['remotion', 'illustrated'].includes(story.mode)) throw new Error('无效的动画模式')
  if (![[1080, 1920], [1920, 1080], [1080, 1080]].some(([w, h]) => story.width === w && story.height === h) || story.fps !== 30) throw new Error('无效的画幅或帧率')
  if (!Array.isArray(story.scenes) || story.scenes.length < 1 || story.scenes.length > 12) throw new Error('无效的分镜')
  let frames = 0
  for (const scene of story.scenes) {
    if (!Number.isInteger(scene.durationInFrames) || scene.durationInFrames < 1 || !['orbit', 'bars', 'steps'].includes(scene.visual)) throw new Error('无效的分镜参数')
    if (typeof scene.title !== 'string' || typeof scene.text !== 'string') throw new Error('缺少分镜文案')
    if (story.mode === 'illustrated' && !/^scene-\d+\.png$/.test(scene.image)) throw new Error('图片必须是当前任务本地素材')
    if (scene.audio !== undefined && !/^scene-\d+\.wav$/.test(scene.audio)) throw new Error('配音必须是当前任务本地 WAV 文件')
    frames += scene.durationInFrames
  }
  if (frames !== story.durationInFrames || frames > 3600) throw new Error('时间轴总帧数不一致或超出 120 秒')
  return story
}
