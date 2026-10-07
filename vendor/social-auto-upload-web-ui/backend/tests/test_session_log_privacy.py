"""账号诊断只记录步骤，不把登录二维码或会话标识写入日志附件。"""

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]


def logger_calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
    ]


def value_names(node):
    # Cookie 条数是诊断计数，不包含 Cookie 值。
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len":
        return set()
    names = {node.id} if isinstance(node, ast.Name) else set()
    for child in ast.iter_child_nodes(node):
        names.update(value_names(child))
    return names


def test_platform_logs_do_not_interpolate_explicit_session_credentials():
    forbidden = {"token", "cookie_str", "cookies", "src", "qr_url", "qr_code_url", "qrcode_url"}
    files = list((BACKEND / "impl").rglob("platform.py")) + list((BACKEND / "blueprints").glob("*.py"))
    violations = []
    for path in files:
        for call in logger_calls(path):
            for arg in call.args:
                exposed = value_names(arg) & forbidden
                if exposed:
                    violations.append(f"{path.relative_to(BACKEND)}:{call.lineno}: {sorted(exposed)}")
    assert not violations, "日志包含会话凭据变量：\n" + "\n".join(violations)


def test_wechat_logs_do_not_include_urls_containing_session_tokens():
    forbidden = {"home_url", "material_url", "album_url", "current_url", "url"}
    for relative in ("impl/weixin_gzh/platform.py", "blueprints/weixin_gzh_bp.py"):
        for call in logger_calls(BACKEND / relative):
            nodes = [node for arg in call.args for node in ast.walk(arg)]
            assert not any(isinstance(node, ast.Name) and node.id in forbidden for node in nodes), f"{relative}:{call.lineno}"
            assert not any(isinstance(node, ast.Attribute) and node.attr == "url" for node in nodes), f"{relative}:{call.lineno}"
