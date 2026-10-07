"""正常浏览器的账号环境入口：同账号持久目录、会话保存、关闭清理。"""
import asyncio
import hashlib
import json
import os
import platform
import shutil
import threading
import uuid
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlsplit

from conf import BASE_DIR, LOGIN_HEADLESS, LOCAL_CHROME_HEADLESS
from util._logger import get_channel_logger

logger = get_channel_logger('browser')
_account_cookie = ContextVar('account_cookie', default=None)
_login_resources = ContextVar('login_resources', default=None)
_profile_lock = threading.Lock()
_active_profiles = set()


def cookie_path(value) -> Path:
    root = (Path(BASE_DIR) / 'cookiesFile').resolve()
    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('账号会话文件必须位于 cookiesFile 目录内')
    return path


@contextmanager
def account_browser_scope(cookie_file=None):
    """登录开始就确定会话文件，使首次登录和后续任务使用同一个环境。"""
    path = cookie_path(cookie_file or f'{uuid.uuid4()}.json')
    token = _account_cookie.set(path)
    try:
        yield path
    finally:
        _account_cookie.reset(token)


@asynccontextmanager
async def login_browser_scope():
    resources = []
    token = _login_resources.set(resources)
    try:
        yield
    finally:
        errors = []
        try:
            for browser in reversed(resources):
                try:
                    await browser.close()
                except Exception as exc:
                    errors.append(exc)
        finally:
            _login_resources.reset(token)
        if errors:
            raise errors[0]


def browser_executable() -> str:
    """使用机器上已安装的正常浏览器，不下载或随机切换伪装环境。"""
    if platform.system() == 'Windows':
        candidates = []
        for env in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
            base = os.environ.get(env)
            if base:
                candidates.append(Path(base) / 'Microsoft/Edge/Application/msedge.exe')
        for env in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = os.environ.get(env)
            if base:
                candidates.append(Path(base) / 'Google/Chrome/Application/chrome.exe')
        for path in candidates:
            if path.is_file():
                return str(path)
        raise RuntimeError('未找到 Microsoft Edge 或 Google Chrome，请先安装正常浏览器')
    raise RuntimeError('当前账号浏览器仅支持 Windows 上的 Microsoft Edge / Google Chrome')


def init():
    try:
        logger.info('账号浏览器已就绪: %s', browser_executable())
    except RuntimeError as exc:
        logger.warning('%s', exc)


def profile_path(state_path: Path) -> Path:
    # 完整文件名参与目录绑定，不与用户日常浏览器的个人资料目录混用。
    relative = state_path.relative_to((Path(BASE_DIR) / 'cookiesFile').resolve())
    return Path(BASE_DIR) / 'browser_profiles' / relative


def delete_account_profile(cookie_file):
    """仅显式删除账号时清理其专用目录；绝不触及浏览器的日常个人资料。"""
    target = profile_path(cookie_path(cookie_file)).resolve()
    root = (Path(BASE_DIR) / 'browser_profiles').resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError('账号环境目录不合法')
    with _profile_lock:
        if os.path.normcase(str(target)) in _active_profiles:
            raise RuntimeError('该账号环境仍在使用，请关闭后再删除')
        if target.exists():
            shutil.rmtree(target)


def _state_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page_access_error(response):
    """只按主页面的明确 HTTP 失败停机，不把广告/统计接口失败猜成账号风控。"""
    request = response.request
    if (response.status not in {401, 403, 412, 429}
            or request.resource_type != 'document'
            or request.frame != request.frame.page.main_frame):
        return None
    host = urlsplit(response.url).hostname or ''
    # 不记录 URL 查询串，创作平台可能把登录 token 放在其中。
    return f'平台页面 {host} 返回 HTTP {response.status}，已停止自动操作，请检查平台页面后再操作'


def _write_state(path: Path, state: dict, marker: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)
    marker.write_text(_state_digest(path), encoding='ascii')


async def _restore_state(context, path: Path, marker: Path):
    if not path.exists():
        return
    digest = _state_digest(path)
    if not marker.exists() or marker.read_text(encoding='ascii') != digest:
        # 仅首次迁移或用户明确重新导入 Cookie 时应用完整快照；平时保留原 profile。
        await context.set_storage_state(path)
        marker.write_text(digest, encoding='ascii')
    else:
        # Chromium 正常退出后不承诺保留 session cookie，补回最后保存的会话 cookie。
        state = json.loads(path.read_text(encoding='utf-8'))
        session_cookies = [item for item in state['cookies'] if item.get('expires') == -1]
        if session_cookies:
            await context.add_cookies(session_cookies)


async def create_browser(headless=None, login_mode=False, *, storage_state=None):
    from playwright.async_api import async_playwright

    state_path = cookie_path(storage_state) if storage_state is not None else _account_cookie.get()
    if state_path is None:
        raise ValueError('创建账号浏览器时必须指定会话文件或登录作用域')
    if headless is None:
        headless = LOGIN_HEADLESS if login_mode else LOCAL_CHROME_HEADLESS
    profile = profile_path(state_path)
    key = os.path.normcase(str(profile.resolve()))
    with _profile_lock:
        if key in _active_profiles:
            raise RuntimeError('该账号的浏览器正在使用中，请先完成或关闭当前窗口')
        _active_profiles.add(key)

    driver = None
    context = None
    try:
        profile.mkdir(parents=True, exist_ok=True)
        driver = await async_playwright().start()
        # 浏览器路径固定到账号，后续不会因新增另一浏览器而悄悄切换。
        executable_file = profile / 'browser-executable.txt'
        executable = executable_file.read_text(encoding='utf-8') if executable_file.exists() else browser_executable()
        if not Path(executable).is_file():
            raise RuntimeError('该账号绑定的浏览器已移除，请恢复安装后再打开账号环境')
        context = await driver.chromium.launch_persistent_context(
            str(profile), executable_path=executable, headless=headless,
            no_viewport=True, args=['--start-maximized'],
        )
        executable_file.write_text(executable, encoding='utf-8')
        marker = profile / 'state-checkpoint.sha256'
        await _restore_state(context, state_path, marker)
    except BaseException:
        try:
            if context is not None:
                await context.close()
        finally:
            try:
                if driver is not None:
                    await driver.stop()
            finally:
                with _profile_lock:
                    _active_profiles.discard(key)
        raise

    browser = context.browser
    browser._sau_context = context
    browser._sau_cookie_path = state_path
    context._sau_cookie_path = state_path
    owner = asyncio.current_task()
    original_close = context.close
    closed = False
    closing = False
    close_task = None
    save_lock = asyncio.Lock()

    async def checkpoint():
        async with save_lock:
            state = await context.storage_state(indexed_db=True)
            _write_state(state_path, state, marker)

    # 平台的明确保存节点也必须走同一把写锁，避免覆盖 autosave 或漏保存 IndexedDB。
    context.save_account_state = checkpoint

    async def autosave():
        try:
            while browser.is_connected():
                await asyncio.sleep(2)
                if not closing and browser.is_connected():
                    await checkpoint()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning('账号会话定期保存失败；关闭前将再次保存')

    saver = asyncio.create_task(autosave())

    async def finish_close(*args, **kwargs):
        nonlocal closed
        try:
            saver.cancel()
            await asyncio.gather(saver, return_exceptions=True)
            try:
                if browser.is_connected():
                    await checkpoint()
            finally:
                if browser.is_connected():
                    await original_close(*args, **kwargs)
        finally:
            try:
                await driver.stop()
            finally:
                with _profile_lock:
                    _active_profiles.discard(key)
                closed = True

    async def close(*args, **kwargs):
        nonlocal closing, close_task
        if closed:
            return
        if close_task is None:
            closing = True
            close_task = asyncio.create_task(finish_close(*args, **kwargs))
        # 关窗/取消可能在保存或停止 autosave 时到达，必须等资源真正释放才交还账号锁。
        try:
            await asyncio.shield(close_task)
        except asyncio.CancelledError:
            await asyncio.shield(close_task)
            raise

    # 平台可能先关 context 再关 browser，统一幂等收尾并在窗口可读时保存会话。
    context.close = close
    browser.close = close

    def disconnected():
        if not closing and owner is not None and not owner.done():
            owner.cancel()

    browser.on('disconnected', disconnected)

    def response_received(response):
        message = page_access_error(response)
        if message and not closing and owner is not None and not owner.done():
            logger.warning('%s', message)
            owner.cancel(message)

    context.on('response', response_received)
    resources = _login_resources.get()
    if resources is not None:
        resources.append(browser)
    return browser


async def create_context(browser):
    """返回账号唯一持久上下文，不再创建每次不同的临时环境。"""
    return browser._sau_context


async def close_browser(browser):
    await browser.close()


async def open_account_page(cookie_file, url):
    """创作中心保持至用户关闭；调用方的账号锁覆盖整个窗口生命周期。"""
    browser = await create_browser(headless=False, storage_state=cookie_file)
    try:
        context = await create_context(browser)
        page = await context.new_page()
        await page.goto(url, wait_until='domcontentloaded')
        while browser.is_connected():
            await asyncio.sleep(0.5)
    finally:
        await browser.close()
