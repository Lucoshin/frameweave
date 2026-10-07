import re
import uuid

from flask import Blueprint, jsonify, request, send_file

from conf import BASE_DIR
from services.speech import synthesize_speech

speech_bp = Blueprint('speech', __name__, url_prefix='/api/v2/speech')
SPEECH_DIR = BASE_DIR / 'speech'


@speech_bp.post('/preview')
def preview():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(code=400, msg='请求必须为 JSON 对象'), 400
    audio_id = uuid.uuid4().hex
    try:
        result = synthesize_speech(body.get('config'), body.get('text'), SPEECH_DIR / f'{audio_id}.wav')
    except ValueError as error:
        return jsonify(code=400, msg=str(error)), 400
    except RuntimeError as error:
        return jsonify(code=502, msg=str(error)), 502
    except OSError:
        return jsonify(code=500, msg='试听音频保存失败，请检查本机保存目录'), 500
    return jsonify(code=200, data={'audioUrl': f'/api/v2/speech/audio/{audio_id}', 'duration': result['duration']})


@speech_bp.get('/audio/<audio_id>')
def audio(audio_id):
    if not re.fullmatch(r'[0-9a-f]{32}', audio_id):
        return jsonify(code=404, msg='试听音频不存在'), 404
    path = SPEECH_DIR / f'{audio_id}.wav'
    if not path.is_file():
        return jsonify(code=404, msg='试听音频不存在'), 404
    return send_file(path, mimetype='audio/wav', conditional=True)
