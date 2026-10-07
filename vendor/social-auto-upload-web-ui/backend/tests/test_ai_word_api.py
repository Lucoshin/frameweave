import json

import pytest

from word_generation.service import WordGenerationService


def test_generate_endpoint_rejects_missing_image_provider_before_charging_text(monkeypatch, tmp_path):
    from app import app
    from blueprints.word_generation_bp import word_generation_service
    calls = []
    monkeypatch.setattr(word_generation_service, '_chat', lambda *_: calls.append(True))
    response = app.test_client().post('/api/v2/word/generate', json={
        'titles': ['图文'], 'prompt': '正文', 'output_directory': str(tmp_path),
        'provider': {'base_url': 'https://example.invalid/v1', 'api_key': 'secret', 'model': 'text'},
        'images': {'mode': 'ai', 'count': 1, 'prompt': '插画'},
    })
    assert response.status_code == 400
    assert '图像' in response.get_json()['msg']
    assert calls == []


def test_generate_endpoint_maps_request_and_returns_partial_item_results(monkeypatch, tmp_path):
    from app import app
    from blueprints.word_generation_bp import word_generation_service

    def fake_chat(prompt, _provider):
        if "失败文章" in prompt:
            raise RuntimeError("模型拒绝了请求")
        return "真实生成的正文。"

    monkeypatch.setattr(word_generation_service, "_chat", fake_chat)

    response = app.test_client().post(
        "/api/v2/word/generate",
        json={
            "titles": ["成功文章", "失败文章"],
            "prompt": "写成自然的新媒体文章",
            "output_directory": str(tmp_path),
            "provider": {
                "provider_id": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "must-not-leak",
                "model": "deepseek-chat",
            },
            "include_title": False,
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == 200
    assert body["data"]["succeeded"] == 1
    assert body["data"]["failed"] == 1
    assert [item["status"] for item in body["data"]["items"]] == [
        "succeeded",
        "failed",
    ]
    assert (tmp_path / "成功文章.docx").is_file()
    assert body["data"]["items"][1]["error"] == "模型拒绝了请求"
    assert "must-not-leak" not in json.dumps(body, ensure_ascii=False)


def test_generate_endpoint_redacts_api_key_from_item_errors(monkeypatch, tmp_path):
    from app import app
    from blueprints.word_generation_bp import word_generation_service

    def fake_chat(_prompt, provider):
        raise RuntimeError(f"调用失败，密钥是 {provider['api_key']}")

    monkeypatch.setattr(word_generation_service, "_chat", fake_chat)

    response = app.test_client().post(
        "/api/v2/word/generate",
        json={
            "titles": ["失败文章"],
            "prompt": "提示词",
            "output_directory": str(tmp_path),
            "provider": {
                "provider_id": "custom",
                "base_url": "https://example.invalid/v1",
                "api_key": "must-not-leak",
                "model": "test-model",
            },
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["items"][0]["status"] == "failed"
    assert body["data"]["items"][0]["error"] == "调用失败，密钥是 ***"
    assert "must-not-leak" not in json.dumps(body, ensure_ascii=False)


def test_generate_endpoint_rejects_non_array_titles_before_running_service(monkeypatch, tmp_path):
    called = False

    def fake_generate_batch(self, **kwargs):
        nonlocal called
        called = True
        return {"provider_id": "custom", "items": [], "succeeded": 0, "failed": 0}

    monkeypatch.setattr(WordGenerationService, "generate_batch", fake_generate_batch)

    from app import app

    response = app.test_client().post(
        "/api/v2/word/generate",
        json={
            "titles": "标题不是数组",
            "prompt": "提示词",
            "output_directory": str(tmp_path),
            "provider": {
                "base_url": "https://example.invalid/v1",
                "api_key": "secret",
                "model": "test-model",
            },
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {"code": 400, "msg": "titles 必须是标题数组"}
    assert called is False


def test_generate_endpoint_rejects_incomplete_provider_before_running_service(monkeypatch, tmp_path):
    called = False

    def fake_generate_batch(self, **kwargs):
        nonlocal called
        called = True
        return {"provider_id": "custom", "items": [], "succeeded": 0, "failed": 0}

    monkeypatch.setattr(WordGenerationService, "generate_batch", fake_generate_batch)

    from app import app

    response = app.test_client().post(
        "/api/v2/word/generate",
        json={
            "titles": ["文章标题"],
            "prompt": "提示词",
            "output_directory": str(tmp_path),
            "provider": {
                "base_url": "https://example.invalid/v1",
                "api_key": "secret",
            },
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "code": 400,
        "msg": "provider 必须包含 base_url、api_key 和 model",
    }
    assert called is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("prompt", "  ", "prompt 必须是非空字符串"),
        ("output_directory", "", "output_directory 必须是非空路径"),
    ],
)
def test_generate_endpoint_rejects_blank_required_fields_before_running_service(
    monkeypatch,
    tmp_path,
    field,
    value,
    message,
):
    called = False

    def fake_generate_batch(self, **kwargs):
        nonlocal called
        called = True
        return {"provider_id": "custom", "items": [], "succeeded": 0, "failed": 0}

    monkeypatch.setattr(WordGenerationService, "generate_batch", fake_generate_batch)
    payload = {
        "titles": ["文章标题"],
        "prompt": "提示词",
        "output_directory": str(tmp_path),
        "provider": {
            "base_url": "https://example.invalid/v1",
            "api_key": "secret",
            "model": "test-model",
        },
    }
    payload[field] = value

    from app import app

    response = app.test_client().post("/api/v2/word/generate", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {"code": 400, "msg": message}
    assert called is False
