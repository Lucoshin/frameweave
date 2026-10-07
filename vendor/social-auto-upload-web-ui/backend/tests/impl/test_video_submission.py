import asyncio
import importlib
import inspect
from unittest.mock import AsyncMock

import pytest

from impl import manual_publish


@pytest.mark.parametrize("platform,url", [
    ("douyin", "https://creator.douyin.com/creator-micro/content/manage"),
    ("xiaohongshu", "https://creator.xiaohongshu.com/publish/success?source=video"),
    ("bilibili", "https://member.bilibili.com/platform/upload/video/frame"),
])
def test_submit_once_and_require_positive_platform_signal(platform, url):
    page = AsyncMock()
    page.url = url
    page.get_by_text = lambda text, exact: page.success_text
    page.success_text.is_visible.return_value = False
    submit = AsyncMock()
    events = []
    asyncio.run(manual_publish.submit_and_confirm(
        page, platform, submit,
        on_submitting=lambda: events.append("submitting"),
        on_confirmed=lambda signal: events.append(signal),
    ))
    submit.assert_awaited_once()
    assert events[0] == "submitting"
    assert len(events) == 2
    if platform == "bilibili":
        page.success_text.wait_for.assert_awaited_once_with(state="visible", timeout=60000)
        assert "稿件投递成功" in events[1]
    else:
        page.wait_for_url.assert_awaited_once()
        assert events[1] == url


@pytest.mark.parametrize("platform", ["douyin", "xiaohongshu", "bilibili"])
def test_missing_success_signal_fails_without_retrying_submit(platform):
    page = AsyncMock()
    page.url = "https://member.bilibili.com/platform/upload/video/frame"
    page.wait_for_url.side_effect = TimeoutError("no success signal")
    page.get_by_text = lambda text, exact: page.success_text
    page.success_text.is_visible.return_value = False
    page.success_text.wait_for.side_effect = TimeoutError("no success signal")
    submit = AsyncMock()
    confirmed = []
    with pytest.raises(RuntimeError, match="未确认"):
        asyncio.run(manual_publish.submit_and_confirm(
            page, platform, submit, on_confirmed=confirmed.append,
        ))
    submit.assert_awaited_once()
    assert confirmed == []


def test_bilibili_success_text_on_unrelated_page_is_not_submission_evidence():
    page = AsyncMock()
    page.url = "https://passport.bilibili.com/login"
    page.get_by_text = lambda text, exact: page.success_text
    page.success_text.is_visible.return_value = False
    with pytest.raises(RuntimeError, match="未确认"):
        asyncio.run(manual_publish.submit_and_confirm(page, "bilibili", AsyncMock()))


def test_success_words_already_in_user_content_cannot_be_confirmation():
    page = AsyncMock()
    page.url = "https://member.bilibili.com/platform/upload/video/frame"
    page.get_by_text = lambda text, exact: page.success_text
    page.success_text.is_visible.return_value = True
    submit = AsyncMock()
    with pytest.raises(RuntimeError, match="提交前"):
        asyncio.run(manual_publish.submit_and_confirm(page, "bilibili", submit))
    submit.assert_not_awaited()


@pytest.mark.parametrize("key,class_name,helper", [
    ("douyin", "DouyinPlatform", "_upload_one_video"),
    ("bilibili", "BilibiliPlatform", "_upload_single_video"),
    ("xiaohongshu", "XiaohongshuPlatform", "_publish_single_video"),
])
def test_platform_forwards_task_callbacks_to_video_upload(monkeypatch, key, class_name, helper):
    module = importlib.import_module(f"impl.{key}.platform")
    platform = getattr(module, class_name)()
    upload = AsyncMock()
    target = module if key == "xiaohongshu" else platform
    monkeypatch.setattr(target, helper, upload)
    monkeypatch.setattr(module, "get_account_name_by_cookie_file", lambda _: "test")
    submitting = lambda: None
    confirmed = lambda signal: None
    result = platform.publish_video(
        title="测试", files=["video.mp4"], account_file=["test.json"], tags=[],
        _prepare_only=False, _on_publish_submitting=submitting, _on_publish_confirmed=confirmed,
    )
    if inspect.isawaitable(result):
        asyncio.run(result)
    assert upload.await_count == 1
    assert upload.call_args.kwargs["on_publish_submitting"] is submitting
    assert upload.call_args.kwargs["on_publish_confirmed"] is confirmed
