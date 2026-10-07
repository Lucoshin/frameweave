"""查询元数据不得隐式上传测试素材；验证路由表而不访问运营账号。"""

import pytest

from app import app


@pytest.mark.parametrize("path", [
    "/api/bilibili/collections",
    "/api/xiaohongshu/collections",
    "/api/xiaohongshu/search-poi",
    "/api/weibo/collections",
    "/api/vivo/search-position",
    "/api/alipay/compilation-search",
    "/api/alipay/music-list",
    "/api/douyin-image/music-search",
    "/api/kuaishou-image/music-search",
])
def test_uploading_metadata_routes_are_removed(path):
    assert path not in {rule.rule for rule in app.url_map.iter_rules()}


def test_existing_douyin_readonly_routes_remain_available():
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/douyin-image/mix-list" in routes
    assert "/api/douyin-image/search-poi" in routes
