import asyncio
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _common_kwargs():
    return {
        "title": "待人工确认",
        "files": ["C:/media/video.mp4"],
        "tags": [],
        "account_file": ["account.json"],
        "enableTimer": False,
        "schedule_time_str": "",
    }


def test_manual_prepare_mode_never_allows_final_click():
    from impl.manual_publish import final_submit_allowed

    assert final_submit_allowed(prepare_only=True, legacy_dry_run=False) is False
    assert final_submit_allowed(prepare_only=True, legacy_dry_run=True) is False
    assert final_submit_allowed(prepare_only=False, legacy_dry_run=True) is False
    assert final_submit_allowed(prepare_only=False, legacy_dry_run=False) is True


def test_douyin_prepare_entry_forces_final_click_guard(monkeypatch):
    from impl.douyin import platform as module

    observed = {}

    async def fake_upload(self, **kwargs):
        observed.update(kwargs)

    monkeypatch.setattr(module, "get_account_name_by_cookie_file", lambda _name: "")
    monkeypatch.setattr(module.DouyinPlatform, "_upload_one_video", fake_upload)

    asyncio.run(
        module.DouyinPlatform().prepare_video(
            **_common_kwargs(),
            _on_prepare_ready=lambda: None,
        )
    )

    assert observed["prepare_only"] is True
    assert callable(observed["on_prepare_ready"])


def test_xiaohongshu_prepare_entry_forces_final_click_guard(monkeypatch):
    from impl.xiaohongshu import platform as module

    observed = {}

    async def fake_publish(**kwargs):
        observed.update(kwargs)

    monkeypatch.setattr(module, "get_account_name_by_cookie_file", lambda _name: "")
    monkeypatch.setattr(module, "_publish_single_video", fake_publish)

    module.XiaohongshuPlatform().prepare_video(
        **_common_kwargs(),
        _on_prepare_ready=lambda: None,
    )

    assert observed["prepare_only"] is True
    assert callable(observed["on_prepare_ready"])


def test_bilibili_prepare_entry_forces_final_click_guard(monkeypatch):
    from impl.bilibili import platform as module

    observed = {}

    async def fake_upload(self, **kwargs):
        observed.update(kwargs)

    monkeypatch.setattr(module, "get_account_name_by_cookie_file", lambda _name: "")
    monkeypatch.setattr(module.BilibiliPlatform, "_upload_single_video", fake_upload)

    module.BilibiliPlatform().prepare_video(
        **_common_kwargs(),
        _on_prepare_ready=lambda: None,
    )

    assert observed["prepare_only"] is True
    assert callable(observed["on_prepare_ready"])
