"""视频发布会话：默认人工确认，显式 auto 仅作用于本次新任务。"""

from __future__ import annotations

import asyncio
import inspect
import threading
import uuid
from datetime import datetime
from typing import Callable

from impl.registry import get_platform
from services.account_operations import account_operations
from storage import resolve_material_path
from util.video_limits import validate_desc_for_platform, validate_title_for_platform


_AUDITED_PLATFORMS = {
    1: "xiaohongshu",
    3: "douyin",
    5: "bilibili",
}


class PreparePublishError(ValueError):
    """准备发布请求不符合已确认契约。"""


def _require_string_list(payload: dict, field: str, *, allow_empty: bool) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PreparePublishError(f"{field} 必须是字符串数组")
    if not allow_empty and not value:
        raise PreparePublishError(f"{field} 不能为空")
    if any(not item.strip() for item in value):
        raise PreparePublishError(f"{field} 不能包含空字符串")
    return value


def _optional_string(payload: dict, field: str, default: str = "") -> str:
    value = payload.get(field, default)
    if not isinstance(value, str):
        raise PreparePublishError(f"{field} 必须是字符串")
    return value


def build_prepare_job(
    payload: dict,
    *,
    path_resolver: Callable[[str], str] = resolve_material_path,
) -> tuple[int, dict]:
    """按前端视频发布配置字段构建平台参数。

    只接收已在三个平台适配器中存在真实处理逻辑的字段；不读取别名、
    不根据相似字段猜测。
    """
    if not isinstance(payload, dict):
        raise PreparePublishError("请求数据必须是 JSON 对象")

    if payload.get("mode", "manual") not in ("manual", "auto"):
        raise PreparePublishError("mode 必须为 manual 或 auto")

    platform_id = payload.get("type")
    if type(platform_id) is not int or platform_id not in _AUDITED_PLATFORMS:
        raise PreparePublishError("暂不支持准备发布的平台")

    title = _optional_string(payload, "title")
    description = _optional_string(payload, "description")
    files = _require_string_list(payload, "fileList", allow_empty=False)
    accounts = _require_string_list(payload, "accountList", allow_empty=False)
    tags = _require_string_list(payload, "tags", allow_empty=True)

    platform_key = _AUDITED_PLATFORMS[platform_id]
    ok, error = validate_title_for_platform(platform_key, title)
    if not ok:
        raise PreparePublishError(error)
    ok, error = validate_desc_for_platform(platform_key, description)
    if not ok:
        raise PreparePublishError(error)

    resolved_files = [path_resolver(path) for path in files]
    thumbnail = path_resolver(_optional_string(payload, "thumbnail"))
    thumbnail_landscape = path_resolver(
        _optional_string(payload, "thumbnailLandscape")
    )
    thumbnail_portrait = path_resolver(
        _optional_string(payload, "thumbnailPortrait")
    )

    activities = payload.get("activities", [])
    if not isinstance(activities, list) or any(
        not isinstance(item, str) for item in activities
    ):
        raise PreparePublishError("activities 必须是字符串数组")

    return platform_id, {
        "title": title,
        "files": resolved_files,
        "tags": tags,
        "activities": activities,
        "account_file": accounts,
        "category": payload.get("category"),
        "enableTimer": payload.get("enableTimer", False),
        "videos_per_day": payload.get("videosPerDay", 1),
        "daily_times": payload.get("dailyTimes"),
        "start_days": payload.get("startDays", 0),
        "thumbnail_path": thumbnail,
        "thumbnail_landscape_path": thumbnail_landscape,
        "thumbnail_portrait_path": thumbnail_portrait,
        "productLink": _optional_string(payload, "productLink"),
        "productTitle": _optional_string(payload, "productTitle"),
        "desc": description,
        "schedule_time_str": _optional_string(payload, "scheduleTime"),
        "ai_content": _optional_string(payload, "aiContent"),
        "creation_declaration": _optional_string(payload, "creationDeclaration"),
        "bili_repost_source": _optional_string(payload, "biliRepostSource"),
        "hotspot": _optional_string(payload, "hotspot"),
        "tag_type": _optional_string(payload, "tag_type"),
        "tag_value": _optional_string(payload, "tag_value"),
        "mini_link": _optional_string(payload, "mini_link"),
        "mix_id": _optional_string(payload, "mix_id"),
        "video_orientation": _optional_string(payload, "videoOrientation"),
        "xhs_collection_id": _optional_string(payload, "collectionId"),
        "xhs_collection_name": _optional_string(payload, "collectionName"),
        "xhs_source_type": _optional_string(payload, "xhsSourceType"),
        "xhs_shoot_location": _optional_string(payload, "xhsShootLocation"),
        "xhs_shoot_date": _optional_string(payload, "xhsShootDate"),
        "xhs_repost_source": _optional_string(payload, "xhsRepostSource"),
        "bili_collection_name": _optional_string(payload, "biliCollectionName"),
    }


class PreparePublishService:
    def __init__(
        self,
        *,
        platform_factory=get_platform,
        path_resolver=resolve_material_path,
        thread_factory=threading.Thread,
    ):
        self._platform_factory = platform_factory
        self._path_resolver = path_resolver
        self._thread_factory = thread_factory
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _create_session(self, platform_id: int) -> dict:
        now = datetime.now().isoformat()
        session = {
            "sessionId": str(uuid.uuid4()),
            "platformId": platform_id,
            "status": "QUEUED",
            "error": "",
            "createdAt": now,
            "updatedAt": now,
        }
        with self._lock:
            self._sessions[session["sessionId"]] = session
        return session

    def _update(self, session_id: str, **changes) -> dict:
        with self._lock:
            session = self._sessions[session_id]
            session.update(changes)
            session["updatedAt"] = datetime.now().isoformat()
            return dict(session)

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            session = self._sessions.get(session_id)
            return dict(session) if session else None

    def start(self, payload: dict) -> dict:
        platform_id, kwargs = build_prepare_job(
            payload,
            path_resolver=self._path_resolver,
        )
        platform = self._platform_factory(platform_id)
        mode = payload.get("mode", "manual")
        entry_name = "publish_video" if mode == "auto" else "prepare_video"
        entry = getattr(platform, entry_name, None) if platform else None
        if not callable(entry):
            raise PreparePublishError("平台适配器未提供所选模式入口")

        lease = account_operations.acquire(kwargs["account_file"], "准备或执行发布")
        session = self._create_session(platform_id)
        session_id = session["sessionId"]
        self._update(session_id, mode=mode, submissionEvidence=[])
        evidence = []

        def on_prepare_ready():
            self._update(session_id, status="WAITING_CONFIRMATION", error="")

        def on_publish_submitting():
            self._update(session_id, status="SUBMITTING", error="")

        def on_publish_confirmed(signal):
            if not isinstance(signal, str) or not signal:
                raise RuntimeError("平台未提供有效提交凭据")
            evidence.append(signal)
            self._update(session_id, submissionEvidence=list(evidence))

        def run():
            self._update(session_id, status="PREPARING", error="")
            try:
                # 模式在启动时固定，不能用全局开关把已有人工确认任务变成自动提交。
                callbacks = {"_on_prepare_ready": on_prepare_ready}
                if mode == "auto":
                    callbacks = {
                        "_prepare_only": False,
                        "_on_publish_submitting": on_publish_submitting,
                        "_on_publish_confirmed": on_publish_confirmed,
                    }
                result = entry(**kwargs, **callbacks)
                if inspect.isawaitable(result):
                    result = asyncio.run(result)

                if mode == "auto":
                    expected_count = len(kwargs["files"]) * len(kwargs["account_file"])
                    if len(evidence) != expected_count:
                        raise RuntimeError("未确认平台提交结果，请先到创作中心核实，避免重复发布")
                    if result is False:
                        raise RuntimeError("平台返回发布失败，请到创作中心核实")
                    self._update(session_id, status="SUBMITTED", error="")
                    return

                current = self.get(session_id)
                if current["status"] != "WAITING_CONFIRMATION":
                    raise RuntimeError("适配器未到达人工确认节点")
                if result is False:
                    raise RuntimeError("发布页面准备失败")
                self._update(session_id, status="CLOSED", error="")
            except (Exception, asyncio.CancelledError) as exc:
                # 点击提交后或人工接管后断开，只能确认结果未知，不能提示重试投稿。
                current = self.get(session_id)
                uncertain = current["status"] in {"SUBMITTING", "WAITING_CONFIRMATION"} or bool(evidence)
                self._update(
                    session_id,
                    status="UNKNOWN" if uncertain else "FAILED",
                    error=("发布结果未确认，请先在平台创作中心核实，勿直接重复发布"
                           if uncertain else (str(exc) or "操作已取消或浏览器已关闭")),
                )
            finally:
                lease.close()

        try:
            worker = self._thread_factory(
                target=run,
                daemon=True,
                name=f"prepare-publish-{session_id}",
            )
            worker.start()
        except BaseException:
            lease.close()
            self._update(session_id, status="FAILED", error="发布工作线程启动失败")
            raise
        return self.get(session_id)
