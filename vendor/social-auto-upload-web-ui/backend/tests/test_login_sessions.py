import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services import login_sessions as login_sessions_module
from services.login_sessions import LoginSessionManager, normalize_login_event


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        ("https://example.test/qr", "progress"),
        ("200", "success"),
        ("500", "error"),
        ("0", "error"),
        ("error", "error"),
        ("failed", "error"),
        ('{"status":"1","msg":"waiting"}', "progress"),
        ('{"status":"200","name":"alice"}', "success"),
        ('{"status":"500","msg":"bad"}', "error"),
        ('{"status":"failed","message":"bad"}', "error"),
        ('{"error":"missing qr"}', "error"),
    ],
)
def test_normalize_login_event_accepts_all_legacy_platform_shapes(raw, status):
    event = normalize_login_event(raw)

    assert isinstance(event, dict)
    assert event["status"] == status
    assert event["status"] in {"progress", "success", "error"}


def test_normalize_login_event_uses_only_canonical_msg_field():
    event = normalize_login_event('{"status":"failed","message":"bad"}')

    assert event["msg"] == "bad"
    assert "message" not in event
    assert "error" not in event


def test_browser_launch_error_has_short_message_and_separate_detail():
    assert hasattr(login_sessions_module, "build_login_failure_event")
    build_login_failure_event = login_sessions_module.build_login_failure_event
    detail = "BrowserType.launch: Target page, context or browser has been closed " + "x" * 500

    event = build_login_failure_event(RuntimeError(detail))

    assert event["status"] == "error"
    assert event["code"] == "BROWSER_LAUNCH_FAILED"
    assert event["msg"] == "浏览器启动失败，请重新尝试"
    assert event["data"]["detail"] == detail
    assert len(event["msg"]) < 30


def _wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


class _SuccessPlatform:
    platform_name = "测试平台"

    async def login(self, session_id, status_queue, account_id=None):
        status_queue.put('{"status":"200","name":"alice"}')


class _NoTerminalPlatform:
    platform_name = "测试平台"

    async def login(self, session_id, status_queue, account_id=None):
        status_queue.put("opening browser")


class _ExplodingPlatform:
    platform_name = "测试平台"

    async def login(self, session_id, status_queue, account_id=None):
        raise RuntimeError("cloak launch failed")


class _BlockingPlatform:
    platform_name = "测试平台"

    def __init__(self):
        self.started = threading.Event()

    async def login(self, session_id, status_queue, account_id=None):
        status_queue.put("browser opened")
        self.started.set()
        await asyncio.Event().wait()


def test_success_is_published_only_after_platform_returns():
    manager = LoginSessionManager()
    session = manager.start("success", _SuccessPlatform())

    assert session is not None
    event = session.events.get(timeout=2)
    assert event["status"] == "success"
    assert event["name"] == "alice"
    _wait_until(lambda: manager.active_session_id is None)


def test_normal_return_without_terminal_becomes_error():
    manager = LoginSessionManager()
    session = manager.start("missing-terminal", _NoTerminalPlatform())

    assert session is not None
    assert session.events.get(timeout=2)["status"] == "progress"
    terminal = session.events.get(timeout=2)
    assert terminal["status"] == "error"
    assert terminal["code"] == "LOGIN_NO_TERMINAL"


def test_ordinary_exception_becomes_error_and_releases_global_slot():
    manager = LoginSessionManager()
    session = manager.start("explodes", _ExplodingPlatform())

    terminal = session.events.get(timeout=2)
    assert terminal["status"] == "error"
    assert terminal["code"] == "LOGIN_FAILED"
    assert terminal["msg"] == "登录任务执行失败，请重新尝试"
    assert terminal["data"]["detail"] == "cloak launch failed"
    _wait_until(lambda: manager.active_session_id is None)
    assert manager.start("next", _SuccessPlatform()) is not None


def test_only_one_session_can_be_active_and_cancel_is_thread_safe():
    manager = LoginSessionManager()
    platform = _BlockingPlatform()
    session = manager.start("first", platform)

    assert session is not None
    assert platform.started.wait(timeout=2)
    assert manager.start("second", _SuccessPlatform()) is None
    assert manager.cancel("first") is True

    assert session.events.get(timeout=2)["status"] == "progress"
    terminal = session.events.get(timeout=2)
    assert terminal["status"] == "error"
    assert terminal["code"] == "LOGIN_CANCELLED"
    _wait_until(lambda: manager.active_session_id is None)


def test_login_route_returns_busy_terminal_and_cancel_endpoint(monkeypatch):
    import app as app_module

    manager = LoginSessionManager()
    platform = _BlockingPlatform()
    monkeypatch.setattr(app_module, "login_sessions", manager)
    monkeypatch.setattr(app_module, "get_platform", lambda _platform_id: platform)

    first_client = app_module.app.test_client()
    second_client = app_module.app.test_client()
    first_response = first_client.get(
        "/login?type=3&id=first",
        buffered=False,
    )
    assert platform.started.wait(timeout=2)

    busy_response = second_client.get(
        "/login?type=5&id=second",
        buffered=True,
    )
    busy_payload = json.loads(
        busy_response.data.decode("utf-8").removeprefix("data: ")
    )
    assert busy_payload["status"] == "error"
    assert busy_payload["code"] == "LOGIN_BUSY"

    cancel_response = second_client.post("/api/login-sessions/first/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.get_json()["code"] == "LOGIN_CANCEL_REQUESTED"

    remaining_events = "".join(
        chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        for chunk in first_response.response
    )
    assert '"status":"error"' in remaining_events
    assert '"code":"LOGIN_CANCELLED"' in remaining_events


class _FakeBrowser:
    def __init__(self):
        self.close_mock = AsyncMock()
        self.close = self.close_mock


class _BrowserBlockingPlatform(_BlockingPlatform):
    def __init__(self, create_browser):
        super().__init__()
        self.create_browser = create_browser
        self.browser = None

    async def login(self, session_id, status_queue, account_id=None):
        self.browser = await self.create_browser()
        self.started.set()
        await asyncio.Event().wait()


def test_cancel_closes_only_browsers_registered_to_login_scope():
    from impl import _browser

    outside_browser = _FakeBrowser()
    login_browser = _FakeBrowser()
    async def registered_browser():
        # 工厂注册资源后由作用域负责取消清理；此处只测试生命周期，不启动真实浏览器。
        _browser._login_resources.get().append(login_browser)
        return login_browser

    manager = LoginSessionManager()
    platform = _BrowserBlockingPlatform(registered_browser)
    session = manager.start("browser-login", platform)
    assert session is not None
    assert platform.started.wait(timeout=2)
    assert manager.cancel("browser-login") is True
    terminal = session.events.get(timeout=2)
    assert terminal["code"] == "LOGIN_CANCELLED"
    _wait_until(lambda: manager.active_session_id is None)

    login_browser.close_mock.assert_awaited_once()
    outside_browser.close_mock.assert_not_awaited()


def test_login_scope_releases_all_registered_browsers_in_reverse_order():
    from impl import _browser

    order = []
    first = _FakeBrowser()
    second = _FakeBrowser()
    first.close_mock.side_effect = lambda: order.append("first")
    second.close_mock.side_effect = lambda: order.append("second")

    async def run():
        assert _browser._login_resources.get() is None
        async with _browser.login_browser_scope():
            _browser._login_resources.get().extend([first, second])
        assert _browser._login_resources.get() is None

    asyncio.run(run())
    assert order == ["second", "first"]
