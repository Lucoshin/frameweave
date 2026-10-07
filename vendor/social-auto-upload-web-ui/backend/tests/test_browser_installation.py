import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from impl import _browser


class FakeBrowser:
    def __init__(self):
        self.connected = True
        self.events = {}

    def is_connected(self):
        return self.connected

    def on(self, name, callback):
        self.events[name] = callback


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(_browser, 'BASE_DIR', tmp_path)
    executable = tmp_path / 'edge.exe'
    executable.touch()
    monkeypatch.setattr(_browser, 'browser_executable', lambda: str(executable))
    instances = []

    async def launch(*args, **kwargs):
        browser = FakeBrowser()
        state = {'cookies': [], 'origins': []}
        async def close(**kwargs):
            browser.connected = False
            if 'disconnected' in browser.events:
                browser.events['disconnected']()
        context = SimpleNamespace(browser=browser, storage_state=AsyncMock(return_value=state),
                                  set_storage_state=AsyncMock(), add_cookies=AsyncMock(), close=close, on=lambda *_: None)
        instances.append((context, args, kwargs))
        return context

    driver = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=AsyncMock(side_effect=launch)), stop=AsyncMock())
    import playwright.async_api
    monkeypatch.setattr(playwright.async_api, 'async_playwright', lambda: SimpleNamespace(start=AsyncMock(return_value=driver)))
    return tmp_path, instances, driver


def test_profile_reuse_and_atomic_checkpoint(environment):
    root, instances, driver = environment
    async def run():
        with _browser.account_browser_scope('one.json'):
            first = await _browser.create_browser(login_mode=True)
            context = await _browser.create_context(first)
            context.storage_state.return_value = {'cookies': [], 'origins': [{'origin': 'https://example.test', 'localStorage': [{'name': 'updated', 'value': 'yes'}]}]}
            await context.close()
            await first.close()
        second = await _browser.create_browser(storage_state='one.json')
        await second.close()
    asyncio.run(run())
    assert instances[0][1][0] == instances[1][1][0]
    assert len(driver.stop.await_args_list) == 2
    assert instances[0][0].storage_state.await_args.kwargs == {'indexed_db': True}
    assert not list((root / 'cookiesFile').glob('*.tmp'))
    assert 'user_agent' not in instances[0][2]
    assert instances[0][2]['args'] == ['--start-maximized']


def test_active_profile_rejects_second_browser_then_releases(environment):
    async def run():
        browser = await _browser.create_browser(storage_state='same.json')
        with pytest.raises(RuntimeError, match='正在使用'):
            await _browser.create_browser(storage_state='same.json')
        other = await _browser.create_browser(storage_state='other.json')
        await other.close()
        await browser.close()
        again = await _browser.create_browser(storage_state='same.json')
        await again.close()
    asyncio.run(run())


def test_existing_snapshot_is_imported_only_when_external_state_changes(environment):
    root, instances, _ = environment
    state = root / 'cookiesFile/one.json'
    state.parent.mkdir()
    state.write_text(json.dumps({'cookies': [], 'origins': []}), encoding='utf-8')
    async def run():
        first = await _browser.create_browser(storage_state=state)
        await first.close()
        second = await _browser.create_browser(storage_state=state)
        await second.close()
        state.write_text(json.dumps({'cookies': [], 'origins': [], 'changed': True}), encoding='utf-8')
        third = await _browser.create_browser(storage_state=state)
        await third.close()
    asyncio.run(run())
    assert instances[0][0].set_storage_state.await_count == 1
    assert instances[1][0].set_storage_state.await_count == 0
    assert instances[2][0].set_storage_state.await_count == 1


def test_launch_failure_releases_profile(environment):
    _, _, driver = environment
    driver.chromium.launch_persistent_context.side_effect = RuntimeError('launch failed')
    async def run():
        for _ in range(2):
            with pytest.raises(RuntimeError, match='launch failed'):
                await _browser.create_browser(storage_state='one.json')
    asyncio.run(run())
    assert driver.stop.await_count == 2


def test_close_failure_still_stops_driver_and_releases(environment):
    _, instances, driver = environment
    async def run():
        first = await _browser.create_browser(storage_state='one.json')
        instances[0][0].storage_state.side_effect = RuntimeError('save failed')
        with pytest.raises(RuntimeError, match='save failed'):
            await first.close()
        second = await _browser.create_browser(storage_state='one.json')
        await second.close()
    asyncio.run(run())
    assert driver.stop.await_count == 2


def test_profile_delete_is_bounded_and_rejects_active(environment):
    root, _, _ = environment
    async def run():
        browser = await _browser.create_browser(storage_state='one.json')
        with pytest.raises(RuntimeError, match='仍在使用'):
            _browser.delete_account_profile('one.json')
        await browser.close()
    asyncio.run(run())
    with pytest.raises(ValueError):
        _browser.delete_account_profile('../outside.json')
    _browser.delete_account_profile('one.json')
    assert not (root / 'browser_profiles/one.json').exists()
    assert (root / 'cookiesFile/one.json').exists()


def test_login_scope_reuses_existing_identity(environment):
    with _browser.account_browser_scope('existing.json') as path:
        assert path == _browser.cookie_path('existing.json')
    with _browser.account_browser_scope() as first:
        pass
    with _browser.account_browser_scope() as second:
        assert first != second
    assert _browser._account_cookie.get() is None

@pytest.mark.parametrize('status', [401, 403, 412, 429])
def test_main_document_rejection_stops_with_redacted_reason(status):
    frame = SimpleNamespace()
    frame.page = SimpleNamespace(main_frame=frame)
    response = SimpleNamespace(status=status, url='https://example.test/page?token=secret', request=SimpleNamespace(resource_type='document', frame=frame))
    message = _browser.page_access_error(response)
    assert f'HTTP {status}' in message
    assert 'example.test' in message
    assert 'secret' not in message and 'token=' not in message
    response.request.resource_type = 'xhr'
    assert _browser.page_access_error(response) is None
    response.request.resource_type = 'document'
    frame.page.main_frame = object()
    assert _browser.page_access_error(response) is None


def test_login_cleanup_continues_when_one_browser_close_fails():
    first = SimpleNamespace(close=AsyncMock())
    second = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError('close failed')))
    async def run():
        with pytest.raises(RuntimeError, match='close failed'):
            async with _browser.login_browser_scope():
                _browser._login_resources.get().extend([first, second])
    asyncio.run(run())
    first.close.assert_awaited_once()
    second.close.assert_awaited_once()
