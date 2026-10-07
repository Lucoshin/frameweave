import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from services.prepare_publish import (  # noqa: E402
    PreparePublishError,
    PreparePublishService,
    build_prepare_job,
)


class _ImmediateThread:
    def __init__(self, *, target, daemon, name):
        self._target = target
        self.daemon = daemon
        self.name = name

    def start(self):
        self._target()


def _payload(**overrides):
    data = {
        "type": 3,
        "title": "测试标题",
        "description": "测试简介",
        "fileList": ["materials/video.mp4"],
        "accountList": ["douyin-account.json"],
        "tags": ["测试"],
        "activities": ["活动"],
        "thumbnailLandscape": "materials/cover-landscape.jpg",
        "thumbnailPortrait": "materials/cover-portrait.jpg",
        "enableTimer": False,
        "videosPerDay": 1,
        "dailyTimes": [],
        "startDays": 0,
        "scheduleTime": "",
        "aiContent": "",
        "productLink": "",
        "productTitle": "",
        "hotspot": "",
        "tag_type": "",
        "tag_value": "",
        "mini_link": "",
        "mix_id": "",
    }
    data.update(overrides)
    return data


def test_build_prepare_job_uses_existing_postvideo_field_contract():
    resolved = []

    def resolve(path):
        resolved.append(path)
        return f"C:/resolved/{Path(path).name}" if path else ""

    platform_id, kwargs = build_prepare_job(_payload(), path_resolver=resolve)

    assert platform_id == 3
    assert kwargs == {
        "title": "测试标题",
        "files": ["C:/resolved/video.mp4"],
        "tags": ["测试"],
        "activities": ["活动"],
        "account_file": ["douyin-account.json"],
        "category": None,
        "enableTimer": False,
        "videos_per_day": 1,
        "daily_times": [],
        "start_days": 0,
        "thumbnail_path": "",
        "thumbnail_landscape_path": "C:/resolved/cover-landscape.jpg",
        "thumbnail_portrait_path": "C:/resolved/cover-portrait.jpg",
        "productLink": "",
        "productTitle": "",
        "desc": "测试简介",
        "schedule_time_str": "",
        "ai_content": "",
        "creation_declaration": "",
        "bili_repost_source": "",
        "hotspot": "",
        "tag_type": "",
        "tag_value": "",
        "mini_link": "",
        "mix_id": "",
        "video_orientation": "",
        "xhs_collection_id": "",
        "xhs_collection_name": "",
        "xhs_source_type": "",
        "xhs_shoot_location": "",
        "xhs_shoot_date": "",
        "xhs_repost_source": "",
        "bili_collection_name": "",
    }
    assert resolved == [
        "materials/video.mp4",
        "",
        "materials/cover-landscape.jpg",
        "materials/cover-portrait.jpg",
    ]


@pytest.mark.parametrize("platform_id", [1, 3, 5])
def test_build_prepare_job_only_accepts_audited_platforms(platform_id):
    actual_id, _ = build_prepare_job(
        _payload(type=platform_id),
        path_resolver=lambda value: value,
    )
    assert actual_id == platform_id


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"type": 2}, "暂不支持准备发布的平台"),
        ({"fileList": []}, "fileList 不能为空"),
        ({"accountList": []}, "accountList 不能为空"),
        ({"tags": "测试"}, "tags 必须是字符串数组"),
    ],
)
def test_build_prepare_job_rejects_invalid_or_unaudited_contract(override, message):
    with pytest.raises(PreparePublishError, match=message):
        build_prepare_job(
            _payload(**override),
            path_resolver=lambda value: value,
        )


def test_prepare_service_calls_prepare_entry_only_and_tracks_manual_ready_state():
    observed = {}
    service = None

    class FakePlatform:
        platform_key = "douyin"

        def publish_video(self, **_kwargs):
            raise AssertionError("准备发布不得调用自动发布入口")

        def prepare_video(self, **kwargs):
            observed["kwargs"] = dict(kwargs)
            kwargs.pop("_on_prepare_ready")()
            observed["ready_status"] = service.get(observed["session_id"])["status"]

    service = PreparePublishService(
        platform_factory=lambda _platform_id: FakePlatform(),
        path_resolver=lambda value: value,
        thread_factory=_ImmediateThread,
    )

    original_create_session = service._create_session

    def capture_session(platform_id):
        session = original_create_session(platform_id)
        observed["session_id"] = session["sessionId"]
        return session

    service._create_session = capture_session
    started = service.start(_payload())

    assert observed["ready_status"] == "WAITING_CONFIRMATION"
    assert observed["kwargs"]["title"] == "测试标题"
    assert "_on_prepare_ready" in observed["kwargs"]
    assert started["status"] == "CLOSED"
    assert service.get(started["sessionId"])["status"] == "CLOSED"


def test_prepare_service_records_platform_error_without_fabricating_success():
    class BrokenPlatform:
        platform_key = "douyin"

        def prepare_video(self, **_kwargs):
            raise RuntimeError("页面结构已变更")

    service = PreparePublishService(
        platform_factory=lambda _platform_id: BrokenPlatform(),
        path_resolver=lambda value: value,
        thread_factory=_ImmediateThread,
    )

    session = service.start(_payload())

    assert session["status"] == "FAILED"
    assert session["error"] == "页面结构已变更"


@pytest.mark.parametrize("mode", ["automatic", "", None, True, 1])
def test_unknown_publish_mode_is_rejected_before_platform_launch(mode):
    service = PreparePublishService(platform_factory=lambda _: pytest.fail("不能启动平台"))
    with pytest.raises(PreparePublishError, match="mode"):
        service.start(_payload(mode=mode))


def test_automatic_mode_requires_platform_confirmation_and_records_evidence():
    class Platform:
        def publish_video(self, **kwargs):
            assert kwargs["_prepare_only"] is False
            kwargs["_on_publish_submitting"]()
            kwargs["_on_publish_confirmed"]("https://creator.douyin.com/creator-micro/content/manage")
            return True

    service = PreparePublishService(
        platform_factory=lambda _: Platform(), path_resolver=lambda value: value,
        thread_factory=_ImmediateThread,
    )
    session = service.start(_payload(mode="auto"))
    assert session["mode"] == "auto"
    assert session["status"] == "SUBMITTED"
    assert session["submissionEvidence"] == ["https://creator.douyin.com/creator-micro/content/manage"]


@pytest.mark.parametrize("result", [True, False, None])
def test_automatic_mode_never_reports_success_from_return_value_alone(result):
    class Platform:
        def publish_video(self, **kwargs):
            return result

    service = PreparePublishService(
        platform_factory=lambda _: Platform(), path_resolver=lambda value: value,
        thread_factory=_ImmediateThread,
    )
    session = service.start(_payload(mode="auto"))
    assert session["status"] == "FAILED"
    assert "未确认" in session["error"]


def test_default_mode_remains_manual_and_never_uses_publish_entry():
    class Platform:
        def prepare_video(self, **kwargs):
            kwargs["_on_prepare_ready"]()

        def publish_video(self, **kwargs):
            pytest.fail("默认模式不得发布")

    service = PreparePublishService(
        platform_factory=lambda _: Platform(), path_resolver=lambda value: value,
        thread_factory=_ImmediateThread,
    )
    session = service.start(_payload())
    assert session["mode"] == "manual"
    assert session["status"] == "CLOSED"


def test_new_auto_task_does_not_change_waiting_manual_task():
    manual_id = None
    observed = {}

    class Platform:
        def prepare_video(self, **kwargs):
            kwargs["_on_prepare_ready"]()
            observed["auto"] = service.start(_payload(mode="auto", accountList=["other-account.json"]))
            observed["manual_during_auto"] = service.get(manual_id)

        def publish_video(self, **kwargs):
            kwargs["_on_publish_submitting"]()
            kwargs["_on_publish_confirmed"]("confirmed by platform")
            return True

    service = PreparePublishService(
        platform_factory=lambda _: Platform(), path_resolver=lambda value: value,
        thread_factory=_ImmediateThread,
    )
    create = service._create_session

    def capture(platform_id):
        nonlocal manual_id
        session = create(platform_id)
        if manual_id is None:
            manual_id = session["sessionId"]
        return session

    service._create_session = capture
    service.start(_payload())
    assert observed["auto"]["status"] == "SUBMITTED"
    assert observed["manual_during_auto"]["status"] == "WAITING_CONFIRMATION"
    assert observed["manual_during_auto"]["mode"] == "manual"


def test_partial_confirmation_does_not_mark_entire_multi_file_task_submitted():
    class Platform:
        def publish_video(self, **kwargs):
            kwargs["_on_publish_confirmed"]("only first file confirmed")
            return True

    service = PreparePublishService(
        platform_factory=lambda _: Platform(), path_resolver=lambda value: value,
        thread_factory=_ImmediateThread,
    )
    session = service.start(_payload(mode="auto", fileList=["one.mp4", "two.mp4"]))
    assert session["status"] == "UNKNOWN"
    assert session["submissionEvidence"] == ["only first file confirmed"]
