"""同一账号的网页登录、检查和投稿共享一个操作占用，冲突立即报错。"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from conf import BASE_DIR


class AccountBusyError(RuntimeError):
    """账号已有操作，调用方应返回 409，不应自动重试。"""


def account_key(cookie_file: str) -> str:
    # 各入口有的持有 DB filePath，有的持有完整路径，必须归一到同一身份。
    root = (Path(BASE_DIR) / "cookiesFile").resolve()
    path = (root / cookie_file).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("账号环境路径不合法")
    return os.path.normcase(str(path))


class AccountOperationLease:
    def __init__(self, manager, keys, operation):
        self._manager = manager
        self.keys = keys
        self.operation = operation

    def close(self):
        with self._manager._lock:
            for key in self.keys:
                if self._manager._active.get(key) is self:
                    del self._manager._active[key]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class AccountOperations:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = {}

    def acquire(self, cookie_files: list[str], operation: str) -> AccountOperationLease:
        keys = tuple(sorted({account_key(path) for path in cookie_files}))
        with self._lock:
            for key in keys:
                active = self._active.get(key)
                if active is not None:
                    raise AccountBusyError(f"该账号正在{active.operation}，请先完成或关闭当前账号窗口")
            lease = AccountOperationLease(self, keys, operation)
            for key in keys:
                self._active[key] = lease
            return lease


account_operations = AccountOperations()
