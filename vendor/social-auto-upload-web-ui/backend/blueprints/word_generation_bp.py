from flask import Blueprint, jsonify, request

from word_generation.service import WordGenerationService


word_generation_bp = Blueprint(
    "word_generation",
    __name__,
    url_prefix="/api/v2/word",
)
word_generation_service = WordGenerationService()


def _redact_api_key_from_item_errors(result, api_key):
    for item in result.get("items", []):
        error = item.get("error")
        if isinstance(error, str):
            item["error"] = error.replace(api_key, "***")


@word_generation_bp.route("/generate", methods=["POST"])
def generate_word_batch():
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("titles"), list):
        return jsonify({"code": 400, "msg": "titles 必须是标题数组"}), 400
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"code": 400, "msg": "prompt 必须是非空字符串"}), 400
    output_directory = data.get("output_directory")
    if not isinstance(output_directory, str) or not output_directory.strip():
        return jsonify(
            {"code": 400, "msg": "output_directory 必须是非空路径"}
        ), 400
    provider = data.get("provider")
    required_provider_fields = ("base_url", "api_key", "model")
    if not isinstance(provider, dict) or any(
        not str(provider.get(field, "")).strip()
        for field in required_provider_fields
    ):
        return jsonify(
            {"code": 400, "msg": "provider 必须包含 base_url、api_key 和 model"}
        ), 400
    try:
        result = word_generation_service.generate_batch(
            titles=data.get("titles"),
            prompt=prompt,
            output_directory=output_directory,
            provider=provider,
            include_title=data.get("include_title", True),
            images=data.get("images"),
        )
    except (TypeError, ValueError) as error:
        return jsonify({"code": 400, "msg": str(error)}), 400
    except Exception:
        return jsonify({"code": 500, "msg": "AI Word 生成失败"}), 500

    _redact_api_key_from_item_errors(result, provider["api_key"])
    message = "生成完成" if result["failed"] == 0 else "生成完成，部分文章失败"
    return jsonify({"code": 200, "msg": message, "data": result}), 200
