"""已明确请求的发布字段失败时必须停止，不能继续最终投稿。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from impl.bilibili.platform import BilibiliPlatform
from impl.bilibili import platform as bili_module


@pytest.mark.parametrize("method,value", [
    ("_set_category", 3),
    ("_set_creation_declaration", "含AI生成内容"),
    ("_set_collection", "我的合集"),
    ("_set_schedule_time", datetime(2030, 1, 2, 10, 30)),
])
def test_requested_field_errors_propagate(method, value):
    page = Mock()
    page.locator.side_effect = RuntimeError("页面控件不可用")
    page.get_by_text.side_effect = RuntimeError("页面控件不可用")
    page.keyboard = SimpleNamespace(press=AsyncMock(side_effect=RuntimeError("页面控件不可用")))
    with pytest.raises(RuntimeError):
        asyncio.run(getattr(BilibiliPlatform, method)(page, value))


def test_repost_source_is_required_before_any_page_operation():
    page = Mock()
    with pytest.raises(ValueError, match="转载来源"):
        asyncio.run(BilibiliPlatform._set_creation_declaration(page, "内容为转载", ""))
    assert page.mock_calls == []


@pytest.mark.parametrize("method,value", [
    ("_set_category", None),
    ("_set_creation_declaration", ""),
    ("_set_collection", ""),
    ("_set_schedule_time", 0),
])
def test_unrequested_optional_fields_do_not_touch_page(method, value):
    page = Mock()
    asyncio.run(getattr(BilibiliPlatform, method)(page, value))
    assert page.mock_calls == []


@pytest.mark.parametrize("method,value", [
    ("_set_category", 3),
    ("_set_creation_declaration", "含AI生成内容"),
    ("_set_collection", "我的合集"),
])
def test_requested_field_missing_control_is_not_silently_skipped(monkeypatch, method, value):
    locator = Mock()
    locator.first = locator
    locator.count = AsyncMock(return_value=0)
    locator.locator.return_value = locator
    page = Mock()
    page.locator.return_value = locator
    page.get_by_text.return_value = locator
    page.keyboard = SimpleNamespace(press=AsyncMock())
    page.screenshot = AsyncMock()
    monkeypatch.setattr(bili_module.asyncio, "sleep", AsyncMock())
    with pytest.raises(RuntimeError):
        asyncio.run(getattr(BilibiliPlatform, method)(page, value))


def test_auto_publish_stops_before_submit_when_declaration_fails(monkeypatch):
    platform = BilibiliPlatform()
    page = Mock()
    page.url = bili_module.BILIBILI_UPLOAD_URL
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.screenshot = AsyncMock()
    page.locator.return_value.first.count = AsyncMock(return_value=1)
    context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
    browser = object()
    monkeypatch.setattr(platform, "create_browser", AsyncMock(return_value=browser))
    monkeypatch.setattr(platform, "create_context", AsyncMock(return_value=context))
    close = AsyncMock()
    monkeypatch.setattr(platform, "close_browser", close)
    for helper in ["_upload_video_file", "_wait_upload_complete", "_fill_title", "_set_category", "_fill_tags", "_fill_desc", "_set_thumbnail"]:
        monkeypatch.setattr(platform, helper, AsyncMock())
    monkeypatch.setattr(platform, "_set_creation_declaration", AsyncMock(side_effect=RuntimeError("创作声明设置失败")))
    monkeypatch.setattr(bili_module.asyncio, "sleep", AsyncMock())
    submit = AsyncMock()
    monkeypatch.setattr(bili_module, "submit_and_confirm", submit)

    with pytest.raises(RuntimeError, match="创作声明设置失败"):
        asyncio.run(platform._upload_single_video("标题", "video.mp4", [], 0, "account.json", prepare_only=False))
    submit.assert_not_called()
    context.close.assert_awaited_once()
    close.assert_awaited_once()
