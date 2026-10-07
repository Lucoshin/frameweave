import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as module
from services import account_operations as operations_module


@pytest.fixture
def isolated_account(tmp_path, monkeypatch):
    monkeypatch.setattr(operations_module, "BASE_DIR", tmp_path)
    cookie_dir = tmp_path / "cookiesFile"
    cookie_dir.mkdir()
    (cookie_dir / "test.json").write_text("{}")
    database = tmp_path / "db.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE user_info(id INTEGER, status INTEGER, type INTEGER, filePath TEXT)")
        conn.execute("INSERT INTO user_info VALUES(1, 1, 5, 'test.json')")
    monkeypatch.setattr(module, "DB_PATH", database)
    monkeypatch.setattr(module, "_get_account_record", lambda _: {"id": 1, "type": 5, "filePath": "test.json"})
    return database, cookie_dir


@pytest.mark.parametrize("result,expected", [(True, "valid"), (False, "unknown"), (RuntimeError("network failed"), "unknown")])
def test_check_distinguishes_unconfirmed_from_expired(isolated_account, monkeypatch, result, expected):
    class Platform:
        async def check_cookie(self, _):
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(module, "get_platform", lambda _: Platform())
    response = module.app.test_client().get("/checkAccount?id=1")
    assert response.status_code == 200
    assert response.json["data"]["status"] == expected
    assert "valid" not in response.json["data"]
    with sqlite3.connect(isolated_account[0]) as conn:
        assert conn.execute("SELECT status FROM user_info").fetchone()[0] == 1


def test_missing_cookie_is_invalid_without_launching_browser(isolated_account, monkeypatch):
    (isolated_account[1] / "test.json").unlink()
    monkeypatch.setattr(module, "get_platform", lambda _: object())
    response = module.app.test_client().get("/checkAccount?id=1")
    assert response.json["data"]["status"] == "invalid"
    with sqlite3.connect(isolated_account[0]) as conn:
        assert conn.execute("SELECT status FROM user_info").fetchone()[0] == 0


@pytest.mark.parametrize("url,method,payload", [
    ("/checkAccount?id=1", "get", None),
    ("/syncProfile", "post", {"id": 1}),
    ("/openCreatorCenter", "post", {"id": 1}),
    ("/deleteAccount?id=1", "get", None),
])
def test_busy_account_routes_fail_before_platform_call(isolated_account, monkeypatch, url, method, payload):
    monkeypatch.setattr(module, "get_platform", lambda _: object())
    with operations_module.account_operations.acquire(["test.json"], "发布"):
        client = module.app.test_client()
        response = getattr(client, method)(url, json=payload)
        assert response.status_code == 409
        assert "正在发布" in response.json["msg"]


def test_upload_cookie_cannot_overwrite_busy_account(isolated_account):
    import io

    with operations_module.account_operations.acquire(["test.json"], "发布"):
        response = module.app.test_client().post("/uploadCookie", data={
            "id": "1", "platform": "5", "file": (io.BytesIO(b'{"cookies": []}'), "test.json"),
        })
    assert response.status_code == 409
    assert (isolated_account[1] / "test.json").read_text() == "{}"


def test_login_account_conflict_is_visible_as_terminal_sse(isolated_account, monkeypatch):
    import json

    monkeypatch.setattr(module, "get_platform", lambda _: object())
    with operations_module.account_operations.acquire(["test.json"], "发布"):
        response = module.app.test_client().get("/login?type=5&id=busy-session&account_id=1")
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"
        chunks = response.get_data(as_text=True).strip().split("\n\n")
    assert len(chunks) == 1
    event = json.loads(chunks[0].removeprefix("data: "))
    assert event["status"] == "error"
    assert event["code"] == "ACCOUNT_BUSY"
    assert "正在发布" in event["msg"]


def test_prepare_endpoint_returns_conflict_for_busy_account(monkeypatch):
    from blueprints import prepare_publish_bp
    from services.account_operations import AccountBusyError

    def conflict(_):
        raise AccountBusyError("该账号正在发布")

    monkeypatch.setattr(prepare_publish_bp.prepare_publish_service, "start", conflict)
    response = module.app.test_client().post("/api/v2/publish/prepare", json={})
    assert response.status_code == 409
    assert response.json["code"] == 409


def test_creator_center_keeps_account_busy_until_window_finishes(isolated_account, monkeypatch):
    import asyncio
    import threading
    import time
    from services.account_operations import AccountBusyError

    opened = threading.Event()
    closed = threading.Event()

    class Platform:
        async def open_creator_center(self, _):
            opened.set()
            await asyncio.to_thread(closed.wait, 2)

    monkeypatch.setattr(module, "get_platform", lambda _: Platform())
    response = module.app.test_client().post("/openCreatorCenter", json={"id": 1})
    try:
        assert response.status_code == 200
        assert opened.wait(2)
        with pytest.raises(AccountBusyError):
            operations_module.account_operations.acquire(["test.json"], "发布")
    finally:
        closed.set()
    deadline = time.monotonic() + 2
    while True:
        try:
            lease = operations_module.account_operations.acquire(["test.json"], "发布")
        except AccountBusyError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)
        else:
            lease.close()
            break


@pytest.mark.parametrize("endpoint", ["/api/v2/tasks", "/api/v2/tasks/old/retry", "/api/v2/tasks/old/cancel"])
def test_retired_publish_writes_never_start_or_requeue_tasks(monkeypatch, endpoint):
    import ext_api

    monkeypatch.setattr(ext_api, "get_task_queue", lambda: pytest.fail("不得访问旧任务队列"))
    response = module.app.test_client().post(endpoint, json={"title": "旧集成请求"})
    assert response.status_code == 410
    assert response.json["code"] == 410


def test_retired_queue_cannot_publish_even_through_direct_python_calls():
    import asyncio
    from ext_api.task_queue import PublishTask, TaskQueue

    queue = TaskQueue()
    task = PublishTask(payload={"account_file": ["never-open.json"]})
    for action in (lambda: queue.add_task(task), lambda: queue.retry_task(task.id), lambda: queue.cancel_task(task.id), lambda: asyncio.run(queue._execute(task))):
        with pytest.raises(RuntimeError, match="停用"):
            action()
    assert queue._started is False
    assert queue.running == {}


@pytest.mark.parametrize("endpoint", ["/api/v2/tasks", "/api/v2/tasks/old/retry", "/api/v2/tasks/old/cancel"])
def test_retired_publish_writes_never_start_or_requeue_tasks(monkeypatch, endpoint):
    import ext_api

    monkeypatch.setattr(ext_api, "get_task_queue", lambda: pytest.fail("不得访问旧任务队列"))
    response = module.app.test_client().post(endpoint, json={"title": "旧集成请求"})
    assert response.status_code == 410
    assert response.json["code"] == 410


def test_retired_queue_cannot_publish_even_through_direct_python_calls():
    import asyncio
    from ext_api.task_queue import PublishTask, TaskQueue

    queue = TaskQueue()
    task = PublishTask(payload={"account_file": ["never-open.json"]})
    for action in (lambda: queue.add_task(task), lambda: queue.retry_task(task.id), lambda: queue.cancel_task(task.id), lambda: asyncio.run(queue._execute(task))):
        with pytest.raises(RuntimeError, match="停用"):
            action()
    assert queue._started is False
    assert queue.running == {}
