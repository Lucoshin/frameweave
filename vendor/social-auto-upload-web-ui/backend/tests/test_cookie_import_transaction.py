"""导入仅验证成功后替换会话；不访问真实浏览器和平台。"""

import asyncio
import json
import sqlite3
from queue import Queue

import pytest

from impl import _browser, base_platform
from impl.bilibili.platform import BilibiliPlatform


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(base_platform, "BASE_DIR", tmp_path)
    monkeypatch.setattr(_browser, "BASE_DIR", tmp_path)
    (tmp_path / "db").mkdir()
    (tmp_path / "cookiesFile").mkdir()
    with sqlite3.connect(tmp_path / "db/database.db") as conn:
        conn.execute("CREATE TABLE user_info (id INTEGER PRIMARY KEY, type INTEGER, filePath TEXT, userName TEXT, status INTEGER, avatar TEXT, stats TEXT)")
        conn.execute("INSERT INTO user_info VALUES (1, 5, 'stable.json', '原账号', 0, 'old-avatar', '[]')")
    (tmp_path / "cookiesFile/stable.json").write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    profile = _browser.profile_path(_browser.cookie_path("stable.json"))
    profile.mkdir(parents=True)
    (profile / "keep.txt").write_text("existing profile")
    return tmp_path


def record(root):
    with sqlite3.connect(root / "db/database.db") as conn:
        return conn.execute("SELECT filePath,userName,status,avatar,stats FROM user_info WHERE id=1").fetchone()


def configure_import(monkeypatch, root, *, result=None, error=None):
    platform = BilibiliPlatform()
    monkeypatch.setattr(platform, "_parse_cookie_to_storage_state", lambda value: ([{"name": "sample", "value": "local-test", "domain": ".example.test", "path": "/"}], []))
    checked = []

    async def sync(filename):
        checked.append(filename)
        profile = _browser.profile_path(_browser.cookie_path(filename))
        profile.mkdir(parents=True, exist_ok=True)
        (profile / "checked.txt").write_text("temporary validation")
        if error:
            raise error
        return result

    monkeypatch.setattr(platform, "sync_profile", sync)
    return platform, checked


@pytest.mark.parametrize("failure", ["empty", "exception"])
def test_failed_reimport_preserves_snapshot_record_and_profile(environment, monkeypatch, failure):
    original_state = (environment / "cookiesFile/stable.json").read_bytes()
    original_record = record(environment)
    platform, checked = configure_import(monkeypatch, environment,
        result={"name": "", "avatar": "", "stats": []},
        error=RuntimeError("访问受限") if failure == "exception" else None)
    with pytest.raises(RuntimeError):
        asyncio.run(platform.import_cookie("local-test", Queue(), account_id=1))
    assert record(environment) == original_record
    assert (environment / "cookiesFile/stable.json").read_bytes() == original_state
    assert (environment / "browser_profiles/stable.json/keep.txt").exists()
    assert checked[0] != "stable.json"
    assert not (environment / "cookiesFile" / checked[0]).exists()
    assert not _browser.profile_path(_browser.cookie_path(checked[0])).exists()


def test_successful_reimport_keeps_account_path_and_replaces_snapshot(environment, monkeypatch):
    platform, checked = configure_import(monkeypatch, environment, result={"name": "新昵称", "avatar": "new-avatar", "stats": []})
    result = asyncio.run(platform.import_cookie("local-test", Queue(), account_id=1))
    assert result["cookie_filename"] == "stable.json"
    assert record(environment)[:3] == ("stable.json", "新昵称", 1)
    assert json.loads((environment / "cookiesFile/stable.json").read_text(encoding="utf-8"))["cookies"][0]["name"] == "sample"
    assert (environment / "browser_profiles/stable.json/keep.txt").exists()
    assert not (environment / "cookiesFile" / checked[0]).exists()
    assert not _browser.profile_path(_browser.cookie_path(checked[0])).exists()


def test_failed_new_import_removes_its_snapshot_and_profile(environment, monkeypatch):
    platform, checked = configure_import(monkeypatch, environment, error=RuntimeError("网络异常"))
    with pytest.raises(RuntimeError):
        asyncio.run(platform.import_cookie("local-test", Queue()))
    assert not (environment / "cookiesFile" / checked[0]).exists()
    assert not _browser.profile_path(_browser.cookie_path(checked[0])).exists()
    with sqlite3.connect(environment / "db/database.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_info").fetchone()[0] == 1


def test_database_failure_rolls_back_reimported_snapshot(environment, monkeypatch):
    platform, checked = configure_import(monkeypatch, environment, result={"name": "新昵称", "avatar": "new-avatar", "stats": []})
    original = (environment / "cookiesFile/stable.json").read_bytes()
    connect = sqlite3.connect

    class FailingCommit(sqlite3.Connection):
        def commit(self):
            # 快照已替换后再模拟提交失败，真实 SQLite 上下文负责回滚行更新。
            raise sqlite3.DatabaseError("commit failed")

    monkeypatch.setattr(base_platform.sqlite3, "connect", lambda *args, **kwargs: connect(*args, factory=FailingCommit, **kwargs))
    with pytest.raises(sqlite3.DatabaseError):
        asyncio.run(platform.import_cookie("local-test", Queue(), account_id=1))
    assert (environment / "cookiesFile/stable.json").read_bytes() == original
    assert record(environment)[:3] == ("stable.json", "原账号", 0)
    assert not _browser.profile_path(_browser.cookie_path(checked[0])).exists()


def test_successful_new_import_keeps_verified_snapshot_and_profile(environment, monkeypatch):
    platform, checked = configure_import(monkeypatch, environment, result={"name": "新账号", "avatar": "new-avatar", "stats": []})
    result = asyncio.run(platform.import_cookie("local-test", Queue()))
    assert result["cookie_filename"] == checked[0]
    assert (environment / "cookiesFile" / checked[0]).exists()
    assert _browser.profile_path(_browser.cookie_path(checked[0])).exists()
    with sqlite3.connect(environment / "db/database.db") as conn:
        assert conn.execute("SELECT filePath,status FROM user_info WHERE id=?", (result["account_id"],)).fetchone() == (checked[0], 1)
