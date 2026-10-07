"""连接用户配置的 TTS 服务；只保存完整、可解码的 WAV 音频。"""
import io
import json
import math
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

MAX_AUDIO_BYTES = 100 * 1024 * 1024


def validate_speech_config(config):
    if not isinstance(config, dict) or config.get('provider') not in ('openai', 'gpt_sovits'):
        raise ValueError('请选择通用 TTS 或 GPT-SoVITS 语音服务')
    fields = ['baseUrl'] + (['model', 'voice'] if config['provider'] == 'openai' else
                            ['refAudioPath', 'promptText', 'promptLanguage', 'textLanguage'])
    if any(not isinstance(config.get(field), str) or not config[field].strip() for field in fields):
        raise ValueError('请在设置中完整填写语音服务配置；音色克隆需要参考音频路径、文本和语言')
    cleaned = {field: config[field].strip() for field in fields}
    parsed = urllib.parse.urlparse(cleaned['baseUrl'])
    if (parsed.scheme not in ('http', 'https') or not parsed.netloc or
            parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('语音服务地址必须为不含凭证或查询参数的 HTTP / HTTPS 地址')
    api_key = config.get('apiKey', '')
    if not isinstance(api_key, str):
        raise ValueError('语音接口密钥必须为文本')
    speed = config.get('speed')
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not 0.5 <= speed <= 2:
        raise ValueError('语速必须介于 0.5 与 2 之间')
    return {**cleaned, 'provider': config['provider'], 'apiKey': api_key.strip(), 'speed': speed}


def synthesize_speech(config, text, output_path):
    config = validate_speech_config(config)
    if not isinstance(text, str) or not text.strip():
        raise ValueError('配音文本不能为空')
    if config['provider'] == 'openai':
        endpoint = '/audio/speech'
        payload = dict(model=config['model'], input=text.strip(), voice=config['voice'],
                       response_format='wav', speed=config['speed'])
    else:
        endpoint = '/tts'
        payload = dict(text=text.strip(), text_lang=config['textLanguage'],
                       ref_audio_path=config['refAudioPath'], prompt_text=config['promptText'],
                       prompt_lang=config['promptLanguage'], speed_factor=config['speed'],
                       media_type='wav', streaming_mode=False)
    headers = {'Content-Type': 'application/json'}
    if config['apiKey']:
        headers['Authorization'] = f"Bearer {config['apiKey']}"
    req = urllib.request.Request(config['baseUrl'].rstrip('/') + endpoint,
                                 data=json.dumps(payload, ensure_ascii=False).encode('utf-8'), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            data = response.read(MAX_AUDIO_BYTES + 1)
    except urllib.error.HTTPError as error:
        # 不转发提供方错误正文，避免接口密钥或参考音频路径被回显到页面。
        raise RuntimeError(f'语音接口返回 HTTP {error.code}，请检查服务配置和音色模型') from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError('语音接口连接失败或超时，请确认服务已启动') from error
    if len(data) > MAX_AUDIO_BYTES:
        raise RuntimeError('语音接口返回的 WAV 超过 100 MB')
    try:
        with wave.open(io.BytesIO(data), 'rb') as audio:
            frames = audio.getnframes()
            frame_size = audio.getnchannels() * audio.getsampwidth()
            # 只读取头部会把截断下载误判为成功，必须确认所有声明的音频帧都存在。
            if not frames or len(audio.readframes(frames)) != frames * frame_size:
                raise ValueError('音频帧缺失')
            duration = frames / audio.getframerate()
    except (wave.Error, EOFError, ValueError, ZeroDivisionError) as error:
        raise RuntimeError('语音接口未返回完整可解码的 PCM WAV 音频') from error
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    return {'path': str(output), 'duration': duration}
