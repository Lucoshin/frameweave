import re
import uuid
from flask import Blueprint, jsonify, request, send_file
from conf import BASE_DIR
from services.animation import AnimationService
from services.ai_images import image_as_png

animation_bp = Blueprint("animation", __name__, url_prefix="/api/v2/animation")
animation_service = AnimationService(BASE_DIR / "animations")


@animation_bp.post("/assets")
def upload_asset():
    image = request.files.get("image")
    if image is None:
        return jsonify(code=400, msg="请选择图片"), 400
    try:
        data = image_as_png(image.read(20 * 1024 * 1024 + 1))
    except ValueError as error:
        return jsonify(code=400, msg=str(error)), 400
    asset_id = uuid.uuid4().hex
    folder = animation_service.root / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{asset_id}.png").write_bytes(data)
    return jsonify(code=200, data={"id": asset_id, "name": image.filename})


@animation_bp.post("/jobs")
def create_job():
    try:
        result = animation_service.create(request.get_json(silent=True))
    except ValueError as error:
        return jsonify(code=400, msg=str(error)), 400
    return jsonify(code=202, data=result), 202


@animation_bp.get("/jobs/<job_id>")
def get_job(job_id):
    job = animation_service.get(job_id)
    if job is None:
        return jsonify(code=404, msg="任务不存在或服务已重启，请重新生成"), 404
    return jsonify(code=200, data=job)


def _artifact(job_id, filename, mimetype):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        return jsonify(code=404, msg="任务不存在"), 404
    job = animation_service.get(job_id)
    path = animation_service.root / "jobs" / job_id / filename
    if not job or job["status"] != "succeeded" or not path.is_file():
        return jsonify(code=404, msg="任务尚未成功生成文件"), 404
    return send_file(path, mimetype=mimetype, as_attachment=request.args.get("download") == "1", download_name=filename, conditional=True)


@animation_bp.get("/jobs/<job_id>/video")
def get_video(job_id):
    return _artifact(job_id, "video.mp4", "video/mp4")


@animation_bp.get("/jobs/<job_id>/story")
def get_story(job_id):
    return _artifact(job_id, "story.json", "application/json")
