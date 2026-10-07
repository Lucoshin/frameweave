import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from app import app  # noqa: E402


def test_prepare_endpoint_returns_background_session(monkeypatch):
    from blueprints import prepare_publish_bp as module

    expected = {
        "sessionId": "session-1",
        "platformId": 3,
        "status": "PREPARING",
        "error": "",
    }
    monkeypatch.setattr(module.prepare_publish_service, "start", lambda payload: expected)

    response = app.test_client().post(
        "/api/v2/publish/prepare",
        json={
            "type": 3,
            "title": "测试",
            "fileList": ["materials/video.mp4"],
            "accountList": ["account.json"],
            "tags": [],
        },
    )

    assert response.status_code == 202
    assert response.get_json() == {
        "code": 202,
        "msg": "正在准备发布页面",
        "data": expected,
    }


def test_prepare_status_endpoint_returns_404_for_unknown_session(monkeypatch):
    from blueprints import prepare_publish_bp as module

    monkeypatch.setattr(module.prepare_publish_service, "get", lambda _session_id: None)

    response = app.test_client().get("/api/v2/publish/prepare/missing")

    assert response.status_code == 404
    assert response.get_json()["data"] is None


def test_prepare_endpoint_rejects_unknown_mode():
    response = app.test_client().post("/api/v2/publish/prepare", json={"mode": "automatic"})
    assert response.status_code == 400
    assert "mode" in response.get_json()["msg"]


def test_prepare_endpoint_preserves_explicit_auto_mode(monkeypatch):
    from blueprints import prepare_publish_bp as module

    def start(payload):
        assert payload["mode"] == "auto"
        return {"sessionId": "auto-1", "mode": "auto", "status": "PREPARING"}

    monkeypatch.setattr(module.prepare_publish_service, "start", start)
    response = app.test_client().post("/api/v2/publish/prepare", json={"mode": "auto"})
    assert response.status_code == 202
    assert response.get_json()["data"]["mode"] == "auto"
