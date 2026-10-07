import React from 'react'
import { AbsoluteFill, Audio, Composition, Img, Sequence, interpolate, registerRoot, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion'

const FONT = '"Microsoft YaHei", "PingFang SC", sans-serif'
const palette = { ink: '#f2eee4', muted: '#989a9b', gold: '#bc9a54', blue: '#6081ff' }

function Graphic({ visual, progress, frame }) {
  if (visual === 'bars') return <div style={{ display: 'flex', alignItems: 'end', gap: 28, height: 300 }}>
    {[0.38, 0.72, 0.52, 0.92, 0.65].map((value, i) => <div key={i} style={{ width: 68, height: value * 300 * progress, background: `linear-gradient(${palette.blue}, #253568)`, borderRadius: '16px 16px 0 0' }} />)}
  </div>
  if (visual === 'steps') return <div style={{ display: 'flex', gap: 22 }}>
    {[1, 2, 3].map((item, i) => <div key={item} style={{ width: 140, height: 170, border: '1px solid #5668a0', background: '#17213c', borderRadius: 30, display: 'grid', placeItems: 'center', fontSize: 68, color: palette.blue, transform: `translateY(${(1 - progress) * (70 + i * 40)}px)` }}>{String(item).padStart(2, '0')}</div>)}
  </div>
  return <div style={{ width: 400, height: 400, position: 'relative', transform: `scale(${0.7 + progress * 0.3}) rotate(${frame * 0.25}deg)` }}>
    {[0, 1, 2].map(i => <div key={i} style={{ position: 'absolute', inset: 25 + i * 45, border: `2px solid ${i === 1 ? palette.gold : palette.blue}`, borderRadius: '50%', transform: `rotateX(${i * 18}deg)` }}><span style={{ position: 'absolute', width: 22, height: 22, background: i === 1 ? palette.gold : palette.blue, borderRadius: '50%', top: '10%', left: '15%', boxShadow: '0 0 35px #6081ff' }} /></div>)}
    <div style={{ position: 'absolute', inset: 145, background: '#d8e0ff', borderRadius: 28, boxShadow: '0 0 80px #456aff', transform: 'rotate(45deg)' }} />
  </div>
}

function Scene({ scene, mode, index, total }) {
  const frame = useCurrentFrame()
  const { fps, width, height } = useVideoConfig()
  const portrait = height > width
  const entrance = spring({ frame, fps, config: { damping: 200 } })
  const opacity = interpolate(frame, [0, 10, scene.durationInFrames - 8, scene.durationInFrames - 1], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  const zoom = interpolate(frame, [0, scene.durationInFrames], [1, 1.08])
  return <AbsoluteFill style={{ opacity, padding: portrait ? '190px 80px 140px' : '120px 140px 80px', justifyContent: 'space-between' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: palette.gold, fontSize: 26, letterSpacing: 5 }}><span>{String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}</span><span>{mode === 'illustrated' ? '图 文 叙 事' : 'MOTION NOTES'}</span></div>
    <div style={{ display: 'flex', flexDirection: portrait ? 'column' : 'row', gap: portrait ? 66 : 90, alignItems: 'center', justifyContent: 'center', flex: 1 }}>
      <div style={{ width: portrait ? '100%' : '52%', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', borderRadius: mode === 'illustrated' ? 12 : 0, height: portrait ? 640 : 530 }}>
        {mode === 'illustrated' ? <Img src={staticFile(scene.image)} style={{ width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom})`, filter: 'contrast(1.04)' }} /> : <Graphic visual={scene.visual} progress={entrance} frame={frame} />}
      </div>
      <div style={{ flex: portrait ? undefined : 1, width: portrait ? '100%' : undefined, transform: `translateY(${(1 - entrance) * 40}px)` }}>
        <div style={{ width: 56, height: 4, background: mode === 'illustrated' ? palette.gold : palette.blue, marginBottom: 30 }} />
        <h1 style={{ fontSize: portrait ? 62 : 58, lineHeight: 1.35, margin: '0 0 32px', fontWeight: 800, overflowWrap: 'anywhere' }}>{scene.title}</h1>
        <div style={{ fontSize: portrait ? 36 : 32, lineHeight: 1.7, color: '#c7c9ce', whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>{scene.text}</div>
      </div>
    </div>
    <div style={{ height: 3, background: '#272c37', width: '100%' }}><div style={{ height: '100%', width: `${frame / scene.durationInFrames * 100}%`, background: palette.gold }} /></div>
  </AbsoluteFill>
}

function Animation(story) {
  let from = 0
  return <AbsoluteFill style={{ backgroundColor: story.mode === 'illustrated' ? '#090b0c' : '#0c1222', color: palette.ink, fontFamily: FONT, backgroundImage: 'linear-gradient(#ffffff06 1px, transparent 1px), linear-gradient(90deg, #ffffff06 1px, transparent 1px)', backgroundSize: '100px 100px' }}>
    {story.scenes.map((scene, index) => {
      const start = from
      from += scene.durationInFrames
      return <Sequence key={index} from={start} durationInFrames={scene.durationInFrames}><Scene scene={scene} index={index} total={story.scenes.length} mode={story.mode} />{scene.audio && <Audio src={staticFile(scene.audio)} />}</Sequence>
    })}
  </AbsoluteFill>
}

const Root = () => <Composition id="MatrixAnimation" component={Animation} width={1080} height={1920} fps={30} durationInFrames={180} calculateMetadata={({ props }) => ({ width: props.width, height: props.height, fps: props.fps, durationInFrames: props.durationInFrames })} />
registerRoot(Root)
