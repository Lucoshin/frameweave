"""
Abstract base class for all social media platform implementations.

Each platform (Douyin, Xiaohongshu, Bilibili, etc.) must subclass BasePlatform
and implement the abstract methods. Browser entry points delegate to
``_browser.py`` (normal browser, persistent account profile).
"""

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from queue import Queue

from conf import BASE_DIR
from util._logger import get_channel_logger

from ._browser import (
    create_browser as _create_browser,
    create_context as _create_context,
    close_browser as _close_browser,
)

_base_logger = get_channel_logger("base_platform")


class BasePlatform(ABC):
    """Abstract base for platform-specific automation logic."""

    platform_id: int = 0
    platform_key: str = ""
    platform_name: str = ""

    # ------------------------------------------------------------------
    # Cookie import capability
    # ------------------------------------------------------------------

    #: True if this platform supports importing accounts from a raw cookie
    #: string (e.g. pasted from browser DevTools).  Subclasses override.
    supports_cookie_import: bool = False

    #: The wildcard domain to attach imported cookies to, e.g. ``".baidu.com"``
    #: for Baijiahao (cookie issued by passport.baidu.com also applies to
    #: baijiahao.baidu.com).  Subclasses override; most platforms can simply
    #: set this to ``f".{platform_key}.com"`` or similar.
    platform_cookie_domain: str = ""

    # ------------------------------------------------------------------
    # Unified browser entry points (delegate to _browser.py / Playwright)
    # ------------------------------------------------------------------

    async def create_browser(self, headless=None, login_mode=False, *, storage_state=None):
        return await _create_browser(headless=headless, login_mode=login_mode, storage_state=storage_state)

    async def create_context(self, browser):
        return await _create_context(browser)

    async def close_browser(self, browser) -> None:
        """由工厂在正常关闭前保存会话，并释放账号环境。"""
        await _close_browser(browser)

    # ------------------------------------------------------------------
    # Abstract operations (every platform must implement)
    # ------------------------------------------------------------------

    @abstractmethod
    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform platform login, pushing progress updates to *status_queue*."""
        ...

    @abstractmethod
    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid."""
        ...

    @abstractmethod
    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the platform creator / upload centre page."""
        ...

    @abstractmethod
    async def sync_profile(self, cookie_file: str):
        """Sync profile information from the platform.

        新约定:返回 dict,包含 name/avatar/stats 三项:
          {
            "name":   str,   # 昵称,失败为空字符串
            "avatar": str,   # 头像 URL,失败为空字符串
            "stats":  [      # 运营数据列表,失败或未实现为 []
              {"ICON": "user", "COUNT": 12345, "NAME": "粉丝", "SORT": 1},
              {"ICON": "like", "COUNT": 678,   "NAME": "获赞", "SORT": 2},
              ...
            ],
          }

        兼容旧实现:若仍返回 2 元组 ``(name, avatar)``,路由层会把 stats 视为 []。
        调用方:写入 user_info.stats(JSON 字符串)。
        """
        ...

    @abstractmethod
    def publish_video(self, **kwargs) -> bool:
        """Publish a video to the platform.  Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # Cookie import (default skeleton + per-platform hook)
    # ------------------------------------------------------------------

    # 注意：_parse_cookie_to_storage_state 不是 @abstractmethod，否则会强制
    # 所有平台实现它。仅当 supports_cookie_import=True 时由子类重写。

    def _parse_cookie_to_storage_state(
        self, cookie_str: str
    ) -> tuple[list[dict], list[dict]]:
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。

        只有 ``supports_cookie_import=True`` 的平台需要重写。基类的默认实现
        直接抛错，由 :meth:`import_cookie` 触发并通过 status_queue 上报。
        子类的典型实现参考 BaijiahaoPlatform。

        Returns:
            ``(cookies, origins)`` —— ``import_cookie`` 会原样写入 storage_state。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support cookie import"
        )

    # Cookie import expires 保守占位（7 天）: 手工导入的 cookie 没有真实 expires，
    # 原始字符串不含过期时间；不能声称该占位值是平台签发的真实有效期。
    _IMPORT_COOKIE_EXPIRES_SECONDS = 7 * 24 * 3600

    async def import_cookie(
        self,
        cookie_str: str,
        status_queue: Queue,
        account_id: int | None = None,
    ) -> dict:
        """验证导入状态后提交；重导入保留原账号路径和持久环境。

        验证使用独立临时环境，避免无效 Cookie 污染原账号；失败不改旧状态。
        已有账号在验证成功后原子替换快照，下一次打开原环境时由浏览器工厂恢复。
        """
        from ._browser import cookie_path as resolve_cookie_path, delete_account_profile

        stage_path = None
        destination = None
        old_snapshot = None
        replaced = False
        succeeded = False
        stage_profile_removed = False
        step = 1
        try:
            status_queue.put(json.dumps({"step": step, "status": "running", "msg": "解析 Cookie"}))
            cookies, origins = self._parse_cookie_to_storage_state(cookie_str)
            if not cookies:
                raise ValueError("未解析到任何 Cookie")

            db_path = Path(BASE_DIR) / "db" / "database.db"
            if account_id is not None:
                with sqlite3.connect(db_path) as conn:
                    record = conn.execute(
                        "SELECT filePath FROM user_info WHERE id=? AND type=?",
                        (account_id, self.platform_id),
                    ).fetchone()
                if record is None:
                    raise ValueError("账号不存在或平台不匹配")
                cookie_filename = record[0]
                destination = resolve_cookie_path(cookie_filename)
                old_snapshot = destination.read_bytes() if destination.exists() else None

            step = 2
            status_queue.put(json.dumps({"step": step, "status": "running", "msg": "创建临时验证环境"}))
            stage_filename = f"{uuid.uuid4()}.json"
            stage_path = resolve_cookie_path(stage_filename)
            stage_path.parent.mkdir(parents=True, exist_ok=True)
            stage_path.write_text(json.dumps({"cookies": cookies, "origins": origins}, ensure_ascii=False), encoding="utf-8")
            if account_id is None:
                cookie_filename = stage_filename
                destination = stage_path

            step = 3
            status_queue.put(json.dumps({"step": step, "status": "running", "msg": "验证并同步用户资料"}))
            result = await self.sync_profile(stage_filename)
            # 现有平台契约包括 dict 和旧平台的二元组，不猜测第三种字段名。
            if isinstance(result, dict):
                name = result.get("name", "")
                avatar = result.get("avatar", "")
                stats = result.get("stats", [])
            elif isinstance(result, tuple) and len(result) == 2:
                name, avatar = result
                stats = []
            else:
                raise RuntimeError("平台未返回有效的账号资料")
            if not isinstance(name, str) or not isinstance(avatar, str) or not isinstance(stats, list):
                raise RuntimeError("平台返回的账号资料格式无效")
            if not name.strip() and not avatar.strip():
                raise RuntimeError("未能确认导入的登录状态，原账号保持不变，请检查平台页面后重试")

            step = 4
            status_queue.put(json.dumps({"step": step, "status": "running", "msg": "保存账号"}))
            if account_id is not None:
                # 验证结束后临时浏览器已关闭；既有账号始终使用原目录。
                delete_account_profile(stage_filename)
                stage_profile_removed = True
            with sqlite3.connect(db_path) as conn:
                if account_id is not None:
                    cursor = conn.execute(
                        "UPDATE user_info SET status=1, userName=?, avatar=?, stats=? WHERE id=? AND type=?",
                        (name, avatar, json.dumps(stats, ensure_ascii=False), account_id, self.platform_id),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("待更新账号已不存在")
                    stage_path.replace(destination)
                    replaced = True
                    account_id_saved = int(account_id)
                else:
                    cursor = conn.execute(
                        "INSERT INTO user_info (type, filePath, userName, status, avatar, stats) VALUES (?, ?, ?, 1, ?, ?)",
                        (self.platform_id, cookie_filename, name, avatar, json.dumps(stats, ensure_ascii=False)),
                    )
                    account_id_saved = cursor.lastrowid
                conn.commit()
            succeeded = True
        except BaseException as exc:
            if replaced:
                # 文件替换和 SQLite 不能共用事务；数据库提交失败时原子回滚快照。
                if old_snapshot is None:
                    destination.unlink(missing_ok=True)
                else:
                    stage_path.write_bytes(old_snapshot)
                    stage_path.replace(destination)
            status_queue.put(json.dumps({"status": "error", "step": step, "msg": f"导入未完成：{exc}"}))
            raise
        finally:
            if stage_path is not None and (account_id is not None or not succeeded):
                if not stage_profile_removed:
                    delete_account_profile(stage_path)
                stage_path.unlink(missing_ok=True)

        status_queue.put(json.dumps({
            "step": 4, "status": "done", "msg": "导入完成",
            "account_id": account_id_saved, "userName": name, "avatar": avatar, "stats": stats,
        }))
        return {
            "account_id": account_id_saved, "userName": name, "avatar": avatar,
            "stats": stats, "cookie_filename": cookie_filename,
        }

    # ------------------------------------------------------------------
    # Optional stubs (override if the platform supports these)
    # ------------------------------------------------------------------

    async def publish_note(self, **kwargs) -> bool:
        """Publish an image note (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support note publishing"
        )

    async def publish_image(self, **kwargs) -> bool:
        """Publish an image post (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support image publishing"
        )

    async def get_statistics(self, **kwargs) -> dict:
        """Fetch account statistics (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support statistics"
        )
