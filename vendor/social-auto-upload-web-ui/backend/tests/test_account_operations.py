import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import account_operations as module
from services.account_operations import AccountBusyError, AccountOperations


def test_same_account_filename_and_absolute_path_conflict_and_release(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "BASE_DIR", tmp_path)
    manager = AccountOperations()
    with manager.acquire(["one.json"], "发布"):
        with pytest.raises(AccountBusyError, match="正在发布"):
            manager.acquire([str(tmp_path / "cookiesFile" / "one.json")], "登录")
        with manager.acquire(["two.json"], "登录"):
            pass
    with manager.acquire(["one.json"], "登录"):
        pass


def test_multi_account_acquisition_is_atomic_and_release_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "BASE_DIR", tmp_path)
    manager = AccountOperations()
    held = manager.acquire(["two.json"], "登录")
    with pytest.raises(AccountBusyError):
        manager.acquire(["one.json", "two.json"], "发布")
    with manager.acquire(["one.json"], "检查"):
        pass
    held.close()
    replacement = manager.acquire(["two.json"], "同步")
    held.close()
    with pytest.raises(AccountBusyError):
        manager.acquire(["two.json"], "检查")
    replacement.close()


def test_rejects_account_paths_outside_cookie_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "BASE_DIR", tmp_path)
    with pytest.raises(ValueError, match="路径"):
        AccountOperations().acquire(["../foreign.json"], "检查")


@pytest.mark.parametrize("stage,expected", [(None, "FAILED"), ("manual", "UNKNOWN"), ("auto", "UNKNOWN")])
def test_cancelled_publish_has_terminal_status_and_releases_account(stage, expected):
    from services.prepare_publish import PreparePublishService

    class Platform:
        def prepare_video(self, **kwargs):
            if stage == "manual":
                kwargs["_on_prepare_ready"]()
            raise asyncio.CancelledError()

        def publish_video(self, **kwargs):
            kwargs["_on_publish_submitting"]()
            raise asyncio.CancelledError()

    class ImmediateThread:
        def __init__(self, *, target, **_):
            self.target = target

        def start(self):
            self.target()

    service = PreparePublishService(platform_factory=lambda _: Platform(), path_resolver=lambda value: value, thread_factory=ImmediateThread)
    payload = {"type": 5, "title": "测试", "fileList": ["video.mp4"], "accountList": ["cancel-test.json"], "tags": [], "mode": "auto" if stage == "auto" else "manual"}
    result = service.start(payload)
    assert result["status"] == expected
    if expected == "UNKNOWN":
        assert "勿直接重复发布" in result["error"]
    with module.account_operations.acquire(["cancel-test.json"], "检查"):
        pass


def test_duplicate_publish_rejected_before_worker_and_cancellation_releases():
    from services.prepare_publish import PreparePublishService

    pending = []

    class DeferredThread:
        def __init__(self, *, target, **_):
            pending.append(target)

        def start(self):
            pass

    class Platform:
        def prepare_video(self, **kwargs):
            raise asyncio.CancelledError()

    service = PreparePublishService(platform_factory=lambda _: Platform(), path_resolver=lambda value: value, thread_factory=DeferredThread)
    payload = {"type": 5, "title": "测试", "fileList": ["video.mp4"], "accountList": ["duplicate-test.json"], "tags": []}
    first = service.start(payload)
    try:
        with pytest.raises(AccountBusyError):
            service.start(payload)
        assert len(pending) == 1
    finally:
        pending[0]()
    assert service.get(first["sessionId"])["status"] == "FAILED"
    with module.account_operations.acquire(["duplicate-test.json"], "登录"):
        pass


def test_existing_account_login_holds_lease_until_cancel_cleanup():
    import threading
    from services.login_sessions import LoginSessionManager

    started = threading.Event()

    class Platform:
        async def login(self, *_, **__):
            started.set()
            await asyncio.Event().wait()

    manager = LoginSessionManager()
    session = manager.start("lease-login", Platform(), account_id="1", cookie_file="login-lease-test.json")
    try:
        assert started.wait(2)
        with pytest.raises(AccountBusyError):
            module.account_operations.acquire(["login-lease-test.json"], "发布")
    finally:
        manager.cancel("lease-login")
    assert session.events.get(timeout=2)["code"] == "LOGIN_CANCELLED"
    with module.account_operations.acquire(["login-lease-test.json"], "发布"):
        pass


def test_failed_worker_start_releases_publish_lease():
    from services.prepare_publish import PreparePublishService

    class Platform:
        def prepare_video(self, **_):
            pytest.fail("thread must not run")

    def broken_thread(**_):
        raise RuntimeError("cannot create thread")

    service = PreparePublishService(platform_factory=lambda _: Platform(), path_resolver=lambda value: value, thread_factory=broken_thread)
    with pytest.raises(RuntimeError, match="cannot create thread"):
        service.start({"type": 5, "title": "测试", "fileList": ["video.mp4"], "accountList": ["failed-start-test.json"], "tags": []})
    with module.account_operations.acquire(["failed-start-test.json"], "检查"):
        pass
