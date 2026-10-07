"""AI 仅产出受约束的分镜数据；固定 Remotion 模板在本机渲染。"""
import json
import math
import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse

from services.ai_images import generate_image, validate_image_config
from word_generation.ai_client import OpenAICompatibleClient

FPS = 30
ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}


def validate_request(data):
    if not isinstance(data, dict):
        raise ValueError("请求必须是对象")
    if data.get("mode") not in ("remotion", "illustrated"):
        raise ValueError("请选择 AI 动画或图文动画模式")
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 6000:
        raise ValueError("创作要求需为 1–6000 字")
    duration, count = data.get("duration"), data.get("sceneCount")
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 6 <= duration <= 120:
        raise ValueError("时长应在 6–120 秒之间")
    if type(count) is not int or not 1 <= count <= 12 or duration / count < 2:
        raise ValueError("分镜需为 1–12 个，每镜至少 2 秒")
    if data.get("aspectRatio") not in ASPECTS:
        raise ValueError("请选择有效画幅")
    config = data.get("textConfig")
    if not isinstance(config, dict) or any(not isinstance(config.get(k), str) or not config[k].strip() for k in ("baseUrl", "apiKey", "model")):
        raise ValueError("请在设置中完善文本 AI 服务地址、密钥和模型")
    parsed = urlparse(config["baseUrl"])
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("文本 AI 服务地址必须是有效的 HTTP(S) 地址")
    source = data.get("imageSource")
    assets = data.get("assetIds", [])
    if data["mode"] == "remotion" and source != "none":
        raise ValueError("AI 动画使用动态图形，无需配图")
    if data["mode"] == "illustrated":
        if source not in ("ai", "local"):
            raise ValueError("图文动画请选择 AI 配图或本地图片")
        if source == "ai":
            validate_image_config(data.get("imageConfig"))
        elif not isinstance(assets, list) or len(assets) != count or any(not isinstance(a, str) or not re.fullmatch(r"[0-9a-f]{32}", a) for a in assets):
            raise ValueError("本地图片数量必须与分镜数量一致，请按镜头顺序添加图片")
    if data.get("narration") is not None:
        from services.speech import validate_speech_config
        validate_speech_config(data["narration"])
    return {**data, "prompt": prompt.strip(), "assetIds": assets}


def generate_story(request):
    config = request["textConfig"]
    prompt = (
        "你是短视频分镜编导。仅输出 JSON，不要代码围栏、HTML、JavaScript 或额外说明。"
        f"为以下需求生成恰好 {request['sceneCount']} 个分镜。总时长 {request['duration']} 秒。"
        "结构为 {\"title\":\"总标题\",\"scenes\":[{\"title\":\"镜头标题\",\"text\":\"字幕文案\","
        "\"imagePrompt\":\"无文字插画描述\",\"visual\":\"orbit\"}]}。"
        "总标题和镜头标题最多 40 字，字幕每镜最多 160 字；imagePrompt 最多 1000 字。"
        "visual 仅允许 orbit、bars、steps，分别为抽象环绕、抽象柱形、步骤卡片。"
        "不要编造数据、引用或真实业务指标；柱形仅作为抽象视觉，不表达数据数值。"
        "图片风格：黑底、象牙白线描蚀刻插画、极少暗金点缀、清晰主体、大量留白、无文字。\n"
        f"创作要求：{request['prompt']}"
    )
    content = OpenAICompatibleClient().chat(prompt, {"base_url": config["baseUrl"], "api_key": config["apiKey"], "model": config["model"]})
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("文本模型未返回约定的 JSON 分镜，请调整模型或创作要求后重试") from error


def _text(value, name, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"AI 分镜 {name} 缺失或超出 {maximum} 字")
    return value.strip()


def validate_story(raw, request):
    if not isinstance(raw, dict) or not isinstance(raw.get("scenes"), list) or len(raw["scenes"]) != request["sceneCount"]:
        raise ValueError("AI 分镜数量与所选镜头数不一致")
    total = round(request["duration"] * FPS)
    base, remainder = divmod(total, request["sceneCount"])
    scenes = []
    for index, scene in enumerate(raw["scenes"]):
        if not isinstance(scene, dict) or scene.get("visual") not in ("orbit", "bars", "steps"):
            raise ValueError(f"第 {index + 1} 镜 visual 必须为 orbit、bars 或 steps")
        scenes.append({
            "title": _text(scene.get("title"), "title", 40),
            "text": _text(scene.get("text"), "text", 160),
            "imagePrompt": _text(scene.get("imagePrompt"), "imagePrompt", 1000),
            "visual": scene["visual"], "durationInFrames": base + (index < remainder),
        })
    width, height = ASPECTS[request["aspectRatio"]]
    return {"title": _text(raw.get("title"), "title", 40), "scenes": scenes,
            "mode": request["mode"], "fps": FPS, "width": width, "height": height, "durationInFrames": total}


class AnimationService:
    def __init__(self, root):
        self.root = Path(root)
        self.jobs = {}
        self.lock = threading.RLock()
        self.render_lock = threading.Lock()

    def create(self, data, background=True):
        request = validate_request(data)
        for asset in request["assetIds"]:
            if not (self.root / "assets" / f"{asset}.png").is_file():
                raise ValueError("所选图片不存在，请重新上传")
        job_id = uuid.uuid4().hex
        directory = self.root / "jobs" / job_id
        directory.mkdir(parents=True)
        job = {"id": job_id, "mode": request["mode"], "status": "queued", "progress": 0, "message": "等待本机渲染任务", "error": ""}
        with self.lock:
            self.jobs[job_id] = job
        if background:
            threading.Thread(target=self._run, args=(job_id, request), daemon=True).start()
        else:
            self._run(job_id, request)
        return self.get(job_id)

    def get(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def _update(self, job_id, **values):
        with self.lock:
            self.jobs[job_id].update(values)

    def _run(self, job_id, request):
        directory = self.root / "jobs" / job_id
        try:
            # 动画任务串行编码，避免多个 Remotion 进程同时争抢本机资源。
            with self.render_lock:
                self._update(job_id, status="running", progress=5, message="AI 正在编写分镜")
                story = validate_story(generate_story(request), request)
                public = directory / "assets"
                public.mkdir()
                for index, scene in enumerate(story["scenes"]):
                    if request["mode"] != "illustrated":
                        continue
                    name = f"scene-{index + 1}.png"
                    self._update(job_id, progress=10 + int(index / len(story["scenes"]) * 35), message=f"准备图片 {index + 1}/{len(story['scenes'])}")
                    if request["imageSource"] == "ai":
                        generate_image(request["imageConfig"], scene["imagePrompt"], public / name)
                    else:
                        shutil.copyfile(self.root / "assets" / f"{request['assetIds'][index]}.png", public / name)
                    scene["image"] = name
                if request.get("narration") is not None:
                    from services.speech import synthesize_speech
                    for index, scene in enumerate(story["scenes"]):
                        self._update(job_id, message=f"生成配音 {index + 1}/{len(story['scenes'])}")
                        name = f"scene-{index + 1}.wav"
                        audio = synthesize_speech(request["narration"], scene["text"], public / name)
                        # 按真实音频时长延长镜头，并留出 0.4 秒尾音，防止固定分镜截断配音。
                        scene["durationInFrames"] = max(scene["durationInFrames"], math.ceil(audio["duration"] * FPS) + 12)
                        scene["audio"] = name
                    story["durationInFrames"] = sum(scene["durationInFrames"] for scene in story["scenes"])
                    if story["durationInFrames"] > 120 * FPS:
                        raise ValueError("配音后视频超过 120 秒，请减少分镜文案或提高语速；未截断音频")
                # 只将分镜与本机资产写盘；密钥仅在当前工作线程中传递。
                (directory / "story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
                self._update(job_id, progress=45, message="准备本机动画渲染")
                self._render(job_id, directory)
                output = directory / "video.mp4"
                if not output.is_file() or output.stat().st_size < 1024:
                    raise RuntimeError("渲染未生成有效 MP4 文件")
                self._update(job_id, status="succeeded", progress=100, message="动画已生成", title=story["title"], videoUrl=f"/api/v2/animation/jobs/{job_id}/video", storyUrl=f"/api/v2/animation/jobs/{job_id}/story", duration=story["durationInFrames"] / FPS)
        except Exception as error:
            message = str(error)
            for key in ("textConfig", "imageConfig", "narration"):
                secret = (request.get(key) or {}).get("apiKey", "")
                if secret:
                    message = message.replace(secret, "***")
            self._update(job_id, status="failed", message="动画生成失败", error=message[:1000])
        finally:
            request.clear()
            (directory / "result.json").write_text(json.dumps(self.get(job_id), ensure_ascii=False), encoding="utf-8")

    def _render(self, job_id, directory):
        default_project = Path(__file__).resolve().parents[4] / "apps" / "animation-renderer"
        project = Path(os.environ.get("MATRIX_ANIMATION_RENDERER", default_project))
        node = os.environ.get("MATRIX_NODE_EXECUTABLE") or shutil.which("node")
        if not node or not (project / "node_modules" / "@remotion" / "renderer").is_dir():
            raise RuntimeError("动画渲染环境未就绪：需安装 Node.js 并在 apps/animation-renderer 执行 npm ci")
        args = [node, str(project / "render.mjs"), str(directory.resolve())]
        process = subprocess.Popen(args, cwd=project, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        timer = threading.Timer(1800, process.kill)
        timer.start()
        errors = []
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    errors.append(line.strip())
                    errors = errors[-8:]
                    continue
                if event.get("type") == "progress":
                    self._update(job_id, progress=45 + round(event["progress"] * 54), message=event["message"])
                elif event.get("type") == "error":
                    errors.append(event["message"])
            if process.wait() != 0:
                raise RuntimeError("本机渲染失败：" + " ".join(errors)[-700:])
        finally:
            timer.cancel()
            process.stdout.close()
