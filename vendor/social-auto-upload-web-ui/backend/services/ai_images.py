"""共享 OpenAI 兼容图像接口；只保存可解码的真实图片，不执行模型输出。"""
import base64
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 20 * 1024 * 1024


def validate_image_config(config):
    if not isinstance(config, dict) or any(
        not isinstance(config.get(field), str) or not config[field].strip()
        for field in ('baseUrl', 'apiKey', 'model')
    ):
        raise ValueError('请在设置中配置图像服务地址、API Key 和图像模型')
    cleaned = {field: config[field].strip() for field in ('baseUrl', 'apiKey', 'model')}
    parsed = urllib.parse.urlparse(cleaned['baseUrl'])
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('图像服务地址必须是 HTTP 或 HTTPS 地址')
    return cleaned


def image_as_png(data):
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError('单张图片不能超过 20 MB')
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ('PNG', 'JPEG', 'WEBP'):
                raise ValueError('图片只支持 PNG、JPEG 和 WebP')
            output = io.BytesIO()
            source.convert('RGBA').save(output, format='PNG')
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError('图片数据无效或无法解码') from error


def generate_image(config, prompt, output_path):
    config = validate_image_config(config)
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('图片提示词不能为空')
    endpoint = config['baseUrl'].rstrip('/') + '/images/generations'
    request = urllib.request.Request(endpoint, data=json.dumps({
        'model': config['model'], 'prompt': prompt.strip(), 'n': 1,
    }, ensure_ascii=False).encode('utf-8'), headers={
        'Authorization': f"Bearer {config['apiKey']}", 'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read(MAX_IMAGE_BYTES * 2).decode('utf-8'))
        try:
            item = payload['data'][0]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError('图像接口响应缺少 data[0]') from error
        if isinstance(item, dict) and item.get('b64_json'):
            try:
                image_data = base64.b64decode(item['b64_json'], validate=True)
            except (ValueError, TypeError) as error:
                raise RuntimeError('图像接口返回无效的 b64_json') from error
        elif isinstance(item, dict) and item.get('url'):
            parsed = urllib.parse.urlparse(item['url'])
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                raise RuntimeError('图像接口返回的 url 必须为 HTTP 或 HTTPS')
            # 图片 CDN 不接收模型接口密钥，避免把凭证转交给另一个域名。
            with urllib.request.urlopen(urllib.request.Request(item['url']), timeout=90) as response:
                image_data = response.read(MAX_IMAGE_BYTES + 1)
        else:
            raise RuntimeError('图像接口响应缺少 data[0].b64_json 或 url')
        png = image_as_png(image_data)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'图像接口返回 HTTP {error.code}，请检查图像模型与服务配置') from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError('图像接口连接失败或超时') from error
    except json.JSONDecodeError as error:
        raise RuntimeError('图像接口未返回有效 JSON') from error
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(png)
    return output_path
