import asyncio

import pytest

from impl import _browser
from tests.test_browser_installation import environment


def test_cancel_during_close_still_releases_account_profile(environment):
    async def run():
        browser = await _browser.create_browser(storage_state='cancel-close.json')
        closing = asyncio.create_task(browser.close())
        await asyncio.sleep(0)
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        try:
            assert not _browser._active_profiles, '取消关闭任务后仍占用账号环境'
            assert not browser.is_connected(), '取消关闭任务后浏览器仍运行'
        finally:
            await browser.close()
    asyncio.run(run())
