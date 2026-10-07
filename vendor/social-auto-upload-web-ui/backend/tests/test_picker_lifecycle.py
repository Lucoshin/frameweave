import asyncio
import importlib
import sys
import threading
from pathlib import Path

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.account_operations import AccountBusyError
from services.picker_tasks import run_picker_task


@pytest.fixture
def picker_loop():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)
    loop.close()


@pytest.fixture(params=["jd", "taobao_guanghe"])
def pool_case(request, monkeypatch):
    module = importlib.import_module(f"impl.{request.param}.picker")

    class Session:
        def __init__(self, account_id, *args):
            self.session_id = account_id
            self.close_calls = 0
            self.close_loop = None
            self.started = threading.Event()
            self.cancelled = threading.Event()

        async def wait(self):
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()

        async def close(self):
            self.close_calls += 1
            self.close_loop = asyncio.get_running_loop()

    class_name = "JdPickerSession" if request.param == "jd" else "GuanghePickerSession"
    monkeypatch.setattr(module, class_name, Session)
    pool = module._SessionPool()

    def create():
        return pool.create("1") if request.param == "jd" else pool.create("1", "test.json")

    return request.param, pool, create


def test_duplicate_picker_does_not_replace_or_lose_original(pool_case):
    _, pool, create = pool_case
    original = create()
    with pytest.raises(AccountBusyError):
        create()
    assert pool.get("1") is original
    assert original.close_calls == 0


def test_timeout_cancels_operation_and_closes_on_own_loop(picker_loop, pool_case):
    _, pool, create = pool_case
    session = create()
    with pytest.raises(TimeoutError):
        run_picker_task(picker_loop, session.wait(), timeout=0.02, cleanup=lambda: pool.close("1", session), session=session)
    assert session.cancelled.is_set()
    assert session.close_calls == 1
    assert session.close_loop is picker_loop
    assert pool.get("1") is None
    assert session._picker_tasks == set()


def test_close_during_open_cancels_initialization_before_releasing_pool(picker_loop, pool_case):
    _, pool, create = pool_case
    session = create()
    failures = []

    def open_request():
        try:
            run_picker_task(picker_loop, session.wait(), timeout=2, cleanup=lambda: pool.close("1", session), session=session)
        except BaseException as exc:
            failures.append(exc)

    requester = threading.Thread(target=open_request, daemon=True)
    requester.start()
    assert session.started.wait(1)
    run_picker_task(picker_loop, pool.close("1"), timeout=1)
    requester.join(timeout=2)
    assert not requester.is_alive()
    assert len(failures) == 1
    assert session.cancelled.is_set()
    assert session.close_calls == 1
    assert session.close_loop is picker_loop
    assert pool.get("1") is None


def test_picker_route_reports_conflict_without_closing_old_session(pool_case, monkeypatch):
    name, pool, create = pool_case
    session = create()
    module = importlib.import_module(f"blueprints.{name}_bp")
    monkeypatch.setattr(module, "pool", pool)
    app = Flask(__name__)
    if name == "jd":
        app.register_blueprint(module.bp)
        endpoint, body = "/api/jd/picker/open", {"accountId": "1"}
    else:
        monkeypatch.setattr(module, "_get_cookie_path_by_account_id", lambda _: "test.json")
        monkeypatch.setattr(module, "_resolve_cookie_path", lambda value: value)
        app.register_blueprint(module.taobao_guanghe_bp)
        endpoint, body = "/api/taobao_guanghe/picker/open", {"account_id": "1", "type": "product"}
    response = app.test_client().post(endpoint, json=body)
    assert response.status_code == 409
    assert "先关闭" in response.json["msg"]
    assert pool.get("1") is session
    assert session.close_calls == 0
