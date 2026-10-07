from flask import Blueprint, jsonify, request

from services.prepare_publish import PreparePublishError, PreparePublishService
from services.account_operations import AccountBusyError


prepare_publish_bp = Blueprint(
    "prepare_publish",
    __name__,
    url_prefix="/api/v2/publish",
)
prepare_publish_service = PreparePublishService()


@prepare_publish_bp.post("/prepare")
def prepare_publish():
    try:
        session = prepare_publish_service.start(request.get_json(silent=True))
    except AccountBusyError as exc:
        return jsonify({"code": 409, "msg": str(exc), "data": None}), 409
    except PreparePublishError as exc:
        return jsonify({"code": 400, "msg": str(exc), "data": None}), 400
    except Exception as exc:
        return jsonify({"code": 500, "msg": str(exc), "data": None}), 500

    return jsonify({
        "code": 202,
        "msg": "正在准备发布页面",
        "data": session,
    }), 202


@prepare_publish_bp.get("/prepare/<session_id>")
def get_prepare_publish(session_id: str):
    session = prepare_publish_service.get(session_id)
    if session is None:
        return jsonify({
            "code": 404,
            "msg": "准备发布会话不存在",
            "data": None,
        }), 404
    return jsonify({"code": 200, "msg": None, "data": session}), 200
