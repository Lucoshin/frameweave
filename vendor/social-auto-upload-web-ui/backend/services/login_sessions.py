"""Thread-safe lifecycle management for interactive login sessions.

Platform implementations still emit several historical queue message shapes.
This module is the protocol boundary: it normalizes those messages, owns the
single global login slot, and guarantees exactly one terminal SSE event after
the platform coroutine and its browser cleanup have finished.
"""

from __future__ import annotations

import asyncio
import json
import threading
from queue import Empty, Queue
from typing import Any, Callable

from impl._browser import account_browser_scope, login_browser_scope
from services.account_operations import account_operations
from util._logger import get_channel_logger


logger = get_channel_logger("login_sessions")

_SUCCESS_STATUSES = {"200", "success"}
_ERROR_STATUSES = {"500", "0", "error", "failed"}
_TERMINAL_STATUSES = {"success", "error"}


def build_login_failure_event(exc: Exception) -> dict[str, Any]:
    """把底层异常拆成用户可读摘要和仅供排障查看的详情。"""

    detail = str(exc) or type(exc).__name__
    if "BrowserType.launch" in detail or "Target page, context or browser" in detail:
        return {
            "status": "error",
            "code": "BROWSER_LAUNCH_FAILED",
            "msg": "浏览器启动失败，请重新尝试",
            "data": {"detail": detail},
        }
    return {
        "status": "error",
        "code": "LOGIN_FAILED",
        "msg": "登录任务执行失败，请重新尝试",
        "data": {"detail": detail},
    }


def normalize_login_event(raw: Any) -> dict[str, Any]:
    """Convert a legacy platform queue message to the public login protocol.

    Public ``status`` values are deliberately limited to ``progress``,
    ``success`` and ``error``. Unknown/raw strings (historically QR image URLs)
    remain progress data; legacy terminal tokens and JSON objects are mapped to
    their canonical terminal status.
    """

    payload: dict[str, Any] | None = None
    raw_text: str | None = None

    if isinstance(raw, dict):
        payload = dict(raw)
    else:
        if isinstance(raw, bytes):
            raw_text = raw.decode("utf-8", errors="replace")
        else:
            raw_text = str(raw)
        stripped = raw_text.strip()
        try:
            parsed = json.loads(stripped)
        except (TypeError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            payload = dict(parsed)

    if payload is None:
        value = (raw_text or "").strip()
        legacy_status = value.lower()
        if legacy_status in _SUCCESS_STATUSES:
            return {"status": "success"}
        if legacy_status in _ERROR_STATUSES:
            return {"status": "error", "msg": "平台登录失败"}
        return {"status": "progress", "data": raw_text or ""}

    legacy_status = str(payload.get("status", "")).strip().lower()
    if legacy_status in _SUCCESS_STATUSES:
        status = "success"
    elif legacy_status in _ERROR_STATUSES or (
        not legacy_status and payload.get("error")
    ):
        status = "error"
    else:
        status = "progress"
    legacy_message = payload.pop("message", None)
    legacy_error = payload.pop("error", None)
    if "msg" not in payload:
        message = legacy_message or legacy_error
        if message:
            payload["msg"] = str(message)
    payload["status"] = status
    return payload


def sse_stream(
    status_queue: Queue,
    *,
    on_disconnect: Callable[[], None] | None = None,
    heartbeat_interval: float = 5.0,
):
    """Yield canonical JSON SSE events and cancel on premature disconnect.

    A JSON progress heartbeat makes a dead local EventSource observable even
    while a platform is waiting indefinitely for the user to scan a QR code.
    """

    terminal_sent = False
    try:
        while True:
            try:
                raw = status_queue.get(timeout=heartbeat_interval)
                event = normalize_login_event(raw)
            except Empty:
                event = {"status": "progress", "code": "HEARTBEAT"}

            is_terminal = event["status"] in _TERMINAL_STATUSES
            if is_terminal:
                # Mark before yielding. If the client closes immediately after
                # receiving this chunk, it was a normal terminal close.
                terminal_sent = True
            yield "data: " + json.dumps(
                event,
                ensure_ascii=False,
                separators=(",", ":"),
            ) + "\n\n"
            if is_terminal:
                return
    finally:
        if not terminal_sent and on_disconnect is not None:
            on_disconnect()


class _PlatformEventSink:
    """Queue-like adapter used by unchanged platform login implementations."""

    def __init__(self) -> None:
        self.events: Queue = Queue()
        self._lock = threading.Lock()
        self._terminal_candidate: dict[str, Any] | None = None
        self._finished = False

    def put(self, raw: Any, block: bool = True, timeout: float | None = None) -> None:
        del block, timeout
        event = normalize_login_event(raw)
        with self._lock:
            if self._finished:
                return
            if event["status"] in _TERMINAL_STATUSES:
                # Do not expose success before the platform's finally blocks
                # have run. An exception during cleanup must still become error.
                if self._terminal_candidate is None:
                    self._terminal_candidate = event
                return
        self.events.put(event)

    def terminal_candidate(self) -> dict[str, Any] | None:
        with self._lock:
            if self._terminal_candidate is None:
                return None
            return dict(self._terminal_candidate)

    def finish(self, terminal: dict[str, Any]) -> None:
        canonical = normalize_login_event(terminal)
        if canonical["status"] not in _TERMINAL_STATUSES:
            raise ValueError("login session finish requires a terminal event")
        with self._lock:
            if self._finished:
                return
            self._finished = True
        self.events.put(canonical)


class LoginSession:
    """One login worker and its cross-thread cancellation handle."""

    def __init__(self, session_id: str, platform: Any, account_id: str | None):
        self.session_id = session_id
        self.platform = platform
        self.account_id = account_id
        self._sink = _PlatformEventSink()
        self.events = self._sink.events
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._cancel_requested = False
        self.account_lease = None
        self.cookie_file = None

    @property
    def cancel_requested(self) -> bool:
        with self._lock:
            return self._cancel_requested

    def bind_running_task(self) -> None:
        """Publish the worker-loop task so Flask threads can cancel it safely."""

        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("login worker has no asyncio task")
        with self._lock:
            self._loop = loop
            self._task = task
            should_cancel = self._cancel_requested
        if should_cancel:
            task.cancel()

    def request_cancel(self) -> bool:
        """Request cancellation on the worker's own event loop, once."""

        with self._lock:
            if self._cancel_requested:
                return True
            self._cancel_requested = True
            loop = self._loop
            task = self._task
        if loop is not None and task is not None and not task.done():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                # The worker may have completed between the lock release and
                # this call. The manager will release the slot in its finally.
                pass
        return True


class LoginSessionManager:
    """Own the process-wide single interactive-login slot."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: LoginSession | None = None

    @property
    def active_session_id(self) -> str | None:
        with self._lock:
            return self._active.session_id if self._active is not None else None

    def start(
        self,
        session_id: str,
        platform: Any,
        account_id: str | None = None,
        cookie_file: str | None = None,
    ) -> LoginSession | None:
        """Start a login, or return ``None`` when the global slot is busy."""

        with self._lock:
            if self._active is not None:
                return None
            session = LoginSession(session_id, platform, account_id)
            session.cookie_file = cookie_file
            if cookie_file is not None:
                session.account_lease = account_operations.acquire([cookie_file], "登录")
            self._active = session

        try:
            thread = threading.Thread(
                target=self._thread_main,
                args=(session,),
                name=f"login-{session_id}",
                daemon=True,
            )
            thread.start()
        except Exception as exc:
            self._release(session)
            session._sink.finish({
                "status": "error",
                "code": "LOGIN_START_FAILED",
                "msg": str(exc),
            })
        return session

    def cancel(self, session_id: str) -> bool:
        """Thread-safely cancel the named active login session."""

        with self._lock:
            session = self._active
            if session is None or session.session_id != session_id:
                return False
        return session.request_cancel()

    def _release(self, session: LoginSession) -> None:
        if session.account_lease is not None:
            session.account_lease.close()
        with self._lock:
            if self._active is session:
                self._active = None

    def _thread_main(self, session: LoginSession) -> None:
        try:
            asyncio.run(self._run(session))
        except Exception as exc:
            # _run handles platform errors. This boundary covers event-loop
            # bootstrap failures so the SSE contract still receives a terminal.
            logger.exception("登录线程异常: %s", session.session_id)
            self._release(session)
            session._sink.finish(build_login_failure_event(exc))

    async def _run(self, session: LoginSession) -> None:
        session.bind_running_task()
        terminal: dict[str, Any]
        try:
            # ContextVar scoping means only browsers created by this login task
            # are closed here; creator-center and prepare flows remain untouched.
            with account_browser_scope(session.cookie_file):
                async with login_browser_scope():
                    await session.platform.login(
                        session.session_id,
                        session._sink,
                        account_id=session.account_id,
                    )
            if session.cancel_requested:
                terminal = {
                    "status": "error",
                    "code": "LOGIN_CANCELLED",
                    "msg": "登录已取消",
                }
            else:
                terminal = session._sink.terminal_candidate() or {
                    "status": "error",
                    "code": "LOGIN_NO_TERMINAL",
                    "msg": "平台登录流程结束但未返回结果",
                }
        except asyncio.CancelledError as exc:
            terminal = {
                "status": "error",
                "code": "LOGIN_CANCELLED",
                "msg": str(exc) or "登录已取消",
            }
        except Exception as exc:
            logger.exception(
                "平台登录异常: session=%s platform=%s",
                session.session_id,
                getattr(session.platform, "platform_name", type(session.platform).__name__),
            )
            terminal = build_login_failure_event(exc)
        finally:
            # browser_scope has completed before this point. Only now may the
            # next login acquire the global interactive-login slot.
            self._release(session)

        session._sink.finish(terminal)
