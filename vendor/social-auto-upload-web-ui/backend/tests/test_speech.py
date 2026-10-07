import io
import json
import urllib.error
import wave

import pytest
from flask import Flask


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 8000)
    return buffer.getvalue()


def config(provider='openai'):
    return dict(provider=provider, baseUrl='http://127.0.0.1:9880', apiKey='',
                model='tts-model', voice='voice', speed=1,
                refAudioPath='D:/reference.wav', promptText='参考音频文本',
                promptLanguage='zh', textLanguage='zh')


@pytest.mark.parametrize('provider', ['openai', 'gpt_sovits'])
def test_synthesizes_real_wav_with_provider_contract(monkeypatch, tmp_path, provider):
    from services.speech import synthesize_speech
    calls = []
    def urlopen(request, timeout):
        calls.append(request)
        return io.BytesIO(wav_bytes())
    monkeypatch.setattr('urllib.request.urlopen', urlopen)
    result = synthesize_speech(config(provider), '你好世界', tmp_path / 'voice.wav')
    assert result == {'path': str(tmp_path / 'voice.wav'), 'duration': 0.5}
    assert (tmp_path / 'voice.wav').read_bytes() == wav_bytes()
    assert calls[0].get_header('Authorization') is None
    if provider == 'openai':
        assert calls[0].full_url.endswith('/audio/speech')
        assert json.loads(calls[0].data) == dict(model='tts-model', input='你好世界', voice='voice', response_format='wav', speed=1)
    else:
        assert calls[0].full_url.endswith('/tts')
        assert json.loads(calls[0].data) == dict(text='你好世界', text_lang='zh', ref_audio_path='D:/reference.wav', prompt_text='参考音频文本', prompt_lang='zh', speed_factor=1, media_type='wav', streaming_mode=False)


@pytest.mark.parametrize('audio', [b'{"error":"unavailable"}', wav_bytes()[:-10]], ids=['json-error', 'truncated-wav'])
def test_rejects_invalid_or_truncated_audio_without_saving(monkeypatch, tmp_path, audio):
    from services.speech import synthesize_speech
    monkeypatch.setattr('urllib.request.urlopen', lambda *args, **kwargs: io.BytesIO(audio))
    with pytest.raises(RuntimeError, match='WAV'):
        synthesize_speech(config(), '你好', tmp_path / 'voice.wav')
    assert not (tmp_path / 'voice.wav').exists()


@pytest.mark.parametrize('change', [{'provider': 'unknown'}, {'baseUrl': 'file:///secret'}, {'speed': 0}, {'speed': float('nan')}, {'model': ''}, {'provider': 'gpt_sovits', 'refAudioPath': ''}])
def test_rejects_incomplete_or_invalid_config(change):
    from services.speech import validate_speech_config
    with pytest.raises(ValueError):
        validate_speech_config({**config(), **change})


def test_http_error_does_not_expose_api_key(monkeypatch, tmp_path):
    from services.speech import synthesize_speech
    def urlopen(request, timeout):
        assert request.get_header('Authorization') == 'Bearer secret-key'
        raise urllib.error.HTTPError(request.full_url, 401, 'secret-key', {}, None)
    monkeypatch.setattr('urllib.request.urlopen', urlopen)
    with pytest.raises(RuntimeError, match='HTTP 401') as error:
        synthesize_speech({**config(), 'apiKey': 'secret-key'}, '你好', tmp_path / 'voice.wav')
    assert 'secret-key' not in str(error.value)


def test_preview_audio_can_be_retrieved_and_paths_are_restricted(monkeypatch, tmp_path):
    import blueprints.speech_bp as module
    monkeypatch.setattr(module, 'SPEECH_DIR', tmp_path)
    monkeypatch.setattr('urllib.request.urlopen', lambda *args, **kwargs: io.BytesIO(wav_bytes()))
    app = Flask(__name__)
    app.register_blueprint(module.speech_bp)
    client = app.test_client()
    response = client.post('/api/v2/speech/preview', json={'config': config(), 'text': '你好'})
    assert response.status_code == 200
    data = response.json['data']
    assert data['duration'] == 0.5
    audio = client.get(data['audioUrl'])
    assert audio.status_code == 200
    assert audio.data == wav_bytes()
    assert client.get('/api/v2/speech/audio/../../conf.py').status_code == 404
    assert client.get('/api/v2/speech/audio/not-a-uuid').status_code == 404
    assert client.post('/api/v2/speech/preview', json={'config': config(), 'text': ''}).status_code == 400


def test_preview_reports_provider_failure_and_rejects_non_object_body(monkeypatch, tmp_path):
    import blueprints.speech_bp as module
    monkeypatch.setattr(module, 'SPEECH_DIR', tmp_path)
    def urlopen(*args, **kwargs):
        raise urllib.error.URLError('service unavailable')
    monkeypatch.setattr('urllib.request.urlopen', urlopen)
    app = Flask(__name__)
    app.register_blueprint(module.speech_bp)
    client = app.test_client()
    response = client.post('/api/v2/speech/preview', json={'config': config(), 'text': '你好'})
    assert response.status_code == 502
    assert '连接失败' in response.json['msg']
    assert list(tmp_path.iterdir()) == []
    assert client.post('/api/v2/speech/preview', json=[]).status_code == 400
    assert client.get('/api/v2/speech/audio/' + 'a' * 32).status_code == 404
