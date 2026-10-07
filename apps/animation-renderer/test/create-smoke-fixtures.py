"""创建明确标注测试的本地渲染夹具；不调用任何 AI / 语音付费接口。"""
import json
import math
import struct
import sys
import wave
from pathlib import Path

root = Path(sys.argv[1]).resolve()
for name in ("silent", "audio"):
    directory = root / name
    (directory / "assets").mkdir(parents=True, exist_ok=True)
    scene = {"title": "本地渲染测试", "text": "这是渲染验收用测试分镜，不是业务生成结果。", "visual": "orbit", "durationInFrames": 180}
    if name == "audio":
        scene["audio"] = "scene-1.wav"
        with wave.open(str(directory / "assets" / scene["audio"]), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"".join(struct.pack("<h", int(4000 * math.sin(2 * math.pi * 440 * i / 24000))) for i in range(132000)))
    story = {"title": "本地渲染测试", "mode": "remotion", "width": 1080, "height": 1920, "fps": 30, "durationInFrames": 180, "scenes": [scene]}
    (directory / "story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
print(root)
