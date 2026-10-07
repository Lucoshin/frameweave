import json
import urllib.error
import urllib.request


class OpenAICompatibleClient:
    """调用 OpenAI 兼容的 chat/completions 接口。"""

    def chat(self, prompt, provider):
        base_url = str(provider.get("base_url", "")).strip().rstrip("/")
        api_key = str(provider.get("api_key", "")).strip()
        model = str(provider.get("model", "")).strip()
        if not base_url or not api_key or not model:
            raise ValueError("AI 服务地址、API Key 和模型不能为空")

        endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        body = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"AI 接口返回 HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise RuntimeError(f"AI 接口连接失败: {error}") from error

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("AI 接口响应缺少 choices[0].message.content") from error
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("AI 接口返回了空内容")
        return content.strip()
