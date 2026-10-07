import json
import base64
import io
from pathlib import Path

from docx import Document
from PIL import Image
import pytest

from word_generation.service import WordGenerationService


def test_illustrated_word_embeds_local_images(tmp_path):
    buffer = io.BytesIO()
    Image.new('RGB', (100, 80), '#123456').save(buffer, format='PNG')
    service = WordGenerationService(chat=lambda *_: '第一段。\n第二段。')
    result = service.generate_batch(titles=['图文'], prompt='写作', output_directory=tmp_path,
        provider={'api_key': 'secret'}, images={'mode': 'local', 'files': [{'name': 'local.png', 'data': base64.b64encode(buffer.getvalue()).decode()}]})
    assert result['succeeded'] == 1
    item = result['items'][0]
    assert len(Document(item['output_path']).inline_shapes) == 1
    assert Path(item['image_paths'][0]).is_file()


def test_ai_image_failure_does_not_report_plain_word_as_success(tmp_path):
    def fail_image(*_):
        raise RuntimeError('图片服务不可用')
    service = WordGenerationService(chat=lambda *_: '正文。', image_generator=fail_image)
    result = service.generate_batch(titles=['图文'], prompt='写作', output_directory=tmp_path,
        provider={'api_key': 'secret'}, images={'mode': 'ai', 'count': 1, 'prompt': '插画', 'provider': {'baseUrl': 'https://example.invalid/v1', 'apiKey': 'image-secret', 'model': 'image-model'}})
    assert result['failed'] == 1
    assert result['items'][0]['error'] == '图片服务不可用'
    assert not (tmp_path / '图文.docx').exists()


def test_invalid_local_image_is_rejected_before_text_generation(tmp_path):
    calls = []
    service = WordGenerationService(chat=lambda *_: calls.append(True))
    with pytest.raises(ValueError, match='图片'):
        service.generate_batch(titles=['图文'], prompt='写作', output_directory=tmp_path,
            provider={'api_key': 'secret'}, images={'mode': 'local', 'files': [{'name': 'bad.png', 'data': 'not-image'}]})
    assert calls == []


def test_image_failure_can_be_retried_without_overwriting_retained_images(tmp_path):
    calls = []
    def generate_image(_config, _prompt, path):
        calls.append(path)
        if len(calls) == 1:
            raise RuntimeError('图片失败')
        Image.new('RGB', (100, 200), 'blue').save(path)
    service = WordGenerationService(chat=lambda *_: '正文。', image_generator=generate_image)
    args = dict(titles=['重试'], prompt='写作', output_directory=tmp_path, provider={'api_key': 'secret'},
        images={'mode': 'ai', 'count': 1, 'prompt': '插画', 'provider': {'baseUrl': 'https://example.invalid/v1', 'apiKey': 'image-secret', 'model': 'image-model'}})
    assert service.generate_batch(**args)['failed'] == 1
    retry = service.generate_batch(**args)
    assert retry['succeeded'] == 1
    assert Path(retry['items'][0]['output_path']).name == '重试 (2).docx'


def test_portrait_picture_fits_word_printable_area(tmp_path):
    buffer = io.BytesIO()
    Image.new('RGB', (100, 1000), 'blue').save(buffer, format='PNG')
    service = WordGenerationService(chat=lambda *_: '正文。')
    result = service.generate_batch(titles=['长图'], prompt='写作', output_directory=tmp_path,
        provider={'api_key': 'secret'}, images={'mode': 'local', 'files': [{'name': 'portrait.png', 'data': base64.b64encode(buffer.getvalue()).decode()}]})
    shape = Document(result['items'][0]['output_path']).inline_shapes[0]
    assert shape.height.inches <= 7
    assert shape.width.inches <= 5.5


def test_ai_illustrations_are_generated_for_each_article_and_embedded(tmp_path):
    prompts = []
    def fake_image(config, prompt, path):
        assert config['model'] == 'image-model'
        prompts.append(prompt)
        Image.new('RGB', (120, 80), ('red' if len(prompts) % 2 else 'blue')).save(path)
        return path
    service = WordGenerationService(chat=lambda *_: '第一段。\n第二段。', image_generator=fake_image)
    result = service.generate_batch(titles=['标题甲', '标题乙'], prompt='写作', output_directory=tmp_path,
        provider={'api_key': 'text-secret'}, images={'mode': 'ai', 'count': 2, 'prompt': '清新插画',
            'provider': {'baseUrl': 'https://example.invalid/v1', 'apiKey': 'image-secret', 'model': 'image-model'}})
    assert result['succeeded'] == 2
    assert len(prompts) == 4
    assert '标题甲' in prompts[0] and '标题乙' in prompts[2]
    assert all(len(Document(item['output_path']).inline_shapes) == 2 for item in result['items'])
    assert 'image-secret' not in json.dumps(result)


def test_generates_real_docx_and_numbers_duplicate_titles(tmp_path):
    prompts = []

    def fake_chat(prompt, _provider):
        prompts.append(prompt)
        return "第一段正文。\n第二段正文。"

    service = WordGenerationService(chat=fake_chat)
    result = service.generate_batch(
        titles=["重复标题", "重复标题"],
        prompt="写成自然的新媒体文章",
        output_directory=tmp_path,
        provider={"base_url": "https://example.invalid", "api_key": "secret", "model": "test"},
        include_title=True,
    )

    assert [item["status"] for item in result["items"]] == ["succeeded", "succeeded"]
    assert [Path(item["output_path"]).name for item in result["items"]] == [
        "重复标题.docx",
        "重复标题 (2).docx",
    ]
    assert all("重复标题" in prompt and "写成自然的新媒体文章" in prompt for prompt in prompts)

    document = Document(result["items"][0]["output_path"])
    assert [paragraph.text for paragraph in document.paragraphs] == [
        "重复标题",
        "第一段正文。",
        "第二段正文。",
    ]


def test_task_snapshot_never_contains_api_key(tmp_path):
    service = WordGenerationService(chat=lambda *_args: "正文。")
    result = service.generate_batch(
        titles=["安全测试"],
        prompt="提示词",
        output_directory=tmp_path,
        provider={"provider_id": "deepseek", "base_url": "https://api.deepseek.com", "api_key": "top-secret", "model": "deepseek-chat"},
    )

    assert "top-secret" not in json.dumps(result, ensure_ascii=False)
    assert result["provider_id"] == "deepseek"


def test_existing_file_is_not_overwritten(tmp_path):
    existing = tmp_path / "已有文章.docx"
    existing.write_bytes(b"keep-me")

    service = WordGenerationService(chat=lambda *_args: "新正文。")
    result = service.generate_batch(
        titles=["已有文章"],
        prompt="提示词",
        output_directory=tmp_path,
        provider={"provider_id": "custom", "api_key": "secret", "model": "test"},
    )

    assert existing.read_bytes() == b"keep-me"
    assert Path(result["items"][0]["output_path"]).name == "已有文章 (2).docx"
