import sqlite3

import pytest

import init_db


@pytest.mark.parametrize("previous, expected", [("pre-publish", "manual"), ("startup", "startup"), ("manual", "manual")])
def test_retired_settings_are_migrated_without_changing_other_preferences(tmp_path, monkeypatch, previous, expected):
    db_path = tmp_path / "db" / "database.db"
    db_path.parent.mkdir()
    monkeypatch.setattr(init_db, "BASE_DIR", tmp_path)
    monkeypatch.setattr(init_db, "DB_PATH", db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", [
            ("accountCheckMode", previous),
            ("proxyUrl", "http://unused-proxy.invalid:8080"),
            ("autoSaveInterval", "20"),
        ])

    init_db.init_database()
    init_db.init_database()

    with sqlite3.connect(db_path) as conn:
        settings = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    assert settings == {"accountCheckMode": expected, "autoSaveInterval": "20"}
