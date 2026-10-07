import base64
import io
import json

import pytest
from PIL import Image


def png_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (40, 30), '#4169ff').save(buffer, format='PNG')
    return buffer.getvalue()


def test_generates_real_png_from_standard_base64_response(monkeypatch, tmp_path):
    from services.ai_images import generate_image

    calls = []
    def urlopen(request, timeout):
        calls.append(request)
        return io.BytesIO(json.dumps({'data': [{'b64_json': base64.b64encode(png_bytes()).decode()}]}).encode())
    monkeypatch.setattr('urllib.request.urlopen', urlopen)
    output = generate_image({'baseUrl': 'https://example.invalid/v1', 'apiKey': 'secret', 'model': 'image-model'}, '插画', tmp_path / 'image.png')
    assert Image.open(output).size == (40, 30)
    assert calls[0].full_url == 'https://example.invalid/v1/images/generations'
    assert json.loads(calls[0].data) == {'model': 'image-model', 'prompt': '插画', 'n': 1}


def test_downloads_url_without_forwarding_api_key(monkeypatch, tmp_path):
    from services.ai_images import generate_image

    calls = []
    def urlopen(request, timeout):
        calls.append(request)
        return io.BytesIO(json.dumps({'data': [{'url': 'https://images.example.invalid/generated.png'}]}).encode() if len(calls) == 1 else png_bytes())
    monkeypatch.setattr('urllib.request.urlopen', urlopen)
    generate_image({'baseUrl': 'https://example.invalid/v1', 'apiKey': 'secret', 'model': 'image-model'}, '插画', tmp_path / 'image.png')
    assert calls[1].get_header('Authorization') is None


def test_image_error_is_explicit_and_redacts_key(monkeypatch, tmp_path):
    from services.ai_images import generate_image
    def urlopen(*args, **kwargs):
        return io.BytesIO(b'{"data": []}')
    monkeypatch.setattr('urllib.request.urlopen', urlopen)
    with pytest.raises(RuntimeError, match='data'):
        generate_image({'baseUrl': 'https://example.invalid/v1', 'apiKey': 'secret', 'model': 'image-model'}, '插画', tmp_path / 'image.png')
    assert not (tmp_path / 'image.png').exists()


def test_missing_image_configuration_is_rejected():
    from services.ai_images import validate_image_config
    with pytest.raises(ValueError, match='图像'):
        validate_image_config({'baseUrl': 'https://example.invalid/v1', 'apiKey': 'secret'})
