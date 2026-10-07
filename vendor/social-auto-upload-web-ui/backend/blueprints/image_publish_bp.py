"""
图集草稿兼容 Blueprint
保留图集草稿的读取、保存与删除接口。
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger

logger = get_channel_logger("image_publish")

image_publish_bp = Blueprint('image_publish', __name__, url_prefix='/api/image-publish')

DB_PATH = BASE_DIR / "db" / "database.db"


def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ========== 草稿管理（已迁移到 /api/v2/drafts，保留兼容接口） ==========
@image_publish_bp.route('/drafts', methods=['GET'])
def get_drafts():
    """获取图集草稿列表（重定向到统一接口）"""
    from ext_api import get_drafts as v2_get_drafts
    # 直接调用 v2 接口，传递 type=image 参数
    from flask import request as req
    # 修改请求参数
    req.args = req.args.copy()
    req.args['type'] = 'image'
    return v2_get_drafts()


@image_publish_bp.route('/drafts', methods=['POST'])
def save_draft():
    """保存图集草稿（重定向到统一接口）"""
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空"}), 400

    draft_data = data.get('draft_data')
    if not draft_data:
        return jsonify({"code": 400, "msg": "草稿数据不能为空"}), 400

    # 从 commonConfig.images 提取 image_ids
    common_config = draft_data.get('commonConfig', {})
    images = common_config.get('images', [])
    image_ids = [img['id'] for img in images] if isinstance(images, list) else []

    draft_id = data.get('id')
    now = datetime.now().isoformat()

    try:
        conn = _get_db()
        if draft_id:
            # 更新现有草稿
            title = _extract_image_draft_title(draft_data)
            channels_summary = _extract_image_channels_summary(draft_data)
            cover_path = _extract_image_draft_cover(draft_data)
            if cover_path:
                changes = conn.execute(
                    """UPDATE drafts SET title=?, cover_path=?, draft_data=?, channels_summary=?, updated_at=? WHERE id=? AND type='image'""",
                    (title, cover_path, json.dumps(draft_data, ensure_ascii=False),
                     json.dumps(channels_summary, ensure_ascii=False), now, draft_id)
                ).rowcount
            else:
                # coverImage 为空时保留原 cover_path
                changes = conn.execute(
                    """UPDATE drafts SET title=?, draft_data=?, channels_summary=?, updated_at=? WHERE id=? AND type='image'""",
                    (title, json.dumps(draft_data, ensure_ascii=False),
                     json.dumps(channels_summary, ensure_ascii=False), now, draft_id)
                ).rowcount
            conn.commit()
            conn.close()
            if changes == 0:
                return jsonify({"code": 404, "msg": "草稿不存在"}), 404
        else:
            # 创建新草稿
            title = _extract_image_draft_title(draft_data)
            channels_summary = _extract_image_channels_summary(draft_data)
            cover_path = _extract_image_draft_cover(draft_data)
            cursor = conn.execute(
                """INSERT INTO drafts (type, title, cover_path, draft_data, channels_summary)
                   VALUES ('image', ?, ?, ?, ?)""",
                (title, cover_path, json.dumps(draft_data, ensure_ascii=False),
                 json.dumps(channels_summary, ensure_ascii=False))
            )
            conn.commit()
            draft_id = cursor.lastrowid
            conn.close()
        return jsonify({"code": 200, "msg": "草稿保存成功", "data": {"id": draft_id}})
    except Exception as e:
        logger.error(f"保存草稿失败: {e}")
        return jsonify({"code": 500, "msg": f"保存失败: {str(e)}"}), 500


def _extract_image_draft_title(draft_data):
    """从图集草稿数据中提取标题"""
    # 优先从 accountOverrides 中获取第一个非空标题（账号级配置）
    account_overrides = draft_data.get('accountOverrides', {})
    for account_id, override in account_overrides.items():
        title = override.get('title', '')
        if title and title.strip():
            return title.strip()[:100]

    # 然后从 platformConfigs 中获取（渠道级配置）
    pc = draft_data.get('platformConfigs', {})
    for key in ['douyin', 'xiaohongshu', 'kuaishou']:
        title = pc.get(key, {}).get('title', '')
        if title and title.strip():
            return title.strip()[:100]

    return '无标题'


def _extract_image_draft_cover(draft_data):
    """从图集草稿数据中提取封面路径"""
    common_config = draft_data.get('commonConfig', {})

    # 优先使用用户选择的封面
    cover = common_config.get('coverImage')
    if cover and isinstance(cover, dict):
        # 优先返回 stored_path（新存储系统）
        stored_path = cover.get('stored_path', '')
        if stored_path:
            return stored_path
        url = cover.get('url', '')
        if url:
            # 去掉 http://localhost:5409 前缀，保留相对路径
            if '://' in url:
                from urllib.parse import urlparse
                url = urlparse(url).path
            return url
        return cover.get('path', '') or cover.get('name', '') or ''

    # 兜底：第一张图片（优先 stored_path，兼容旧 path 字段）
    images = common_config.get('images', [])
    if images:
        img = images[0]
        if isinstance(img, dict):
            return img.get('stored_path', '') or img.get('path', '') or img.get('name', '') or ''
    return ''


def _extract_image_channels_summary(draft_data):
    """从图集草稿数据中提取渠道摘要"""
    publish_account_ids = draft_data.get('publishAccountIds', [])
    if not publish_account_ids:
        return []

    # 平台ID到名称和key的映射
    # 注意: platform key 必须与 frontend config/platforms.js 的 key 一致,
    # 否则草稿箱 getPlatformLogo() 匹配不到 logo。
    platform_id_to_name = {
        1: ('xiaohongshu', '小红书'),
        2: ('channels', '视频号'),
        3: ('douyin', '抖音'),
        4: ('kuaishou', '快手'),
        5: ('bilibili', 'B站'),
        6: ('baijiahao', '百家号'),
        11: ('weibo', '微博'),
        12: ('alipay', '支付宝'),   # 图集发布
        13: ('toutiao', '今日头条'),
    }

    try:
        conn = _get_db()
        placeholders = ','.join(['?'] * len(publish_account_ids))
        rows = conn.execute(
            f"SELECT id, type FROM user_info WHERE id IN ({placeholders})",
            publish_account_ids
        ).fetchall()
        conn.close()

        # 统计每个平台的账号数
        counts = {}  # platform_key -> {'name': ..., 'count': ...}
        for row in rows:
            ptype = row['type']
            key, name = platform_id_to_name.get(ptype, (str(ptype), f'平台{ptype}'))
            if key not in counts:
                counts[key] = {'name': name, 'count': 0}
            counts[key]['count'] += 1

        return [{"platform": key, "name": info['name'], "count": info['count']}
                for key, info in counts.items()]
    except Exception:
        return []


@image_publish_bp.route('/drafts/<draft_id>', methods=['DELETE'])
def delete_draft(draft_id):
    """删除图集草稿"""
    try:
        conn = _get_db()
        changes = conn.execute("DELETE FROM drafts WHERE id = ? AND type='image'", (draft_id,)).rowcount
        conn.commit()
        conn.close()

        if changes == 0:
            return jsonify({"code": 404, "msg": "草稿不存在"}), 404

        return jsonify({"code": 200, "msg": "草稿已删除"})
    except Exception as e:
        logger.error(f"删除草稿失败: {e}")
        return jsonify({"code": 500, "msg": f"删除失败: {str(e)}"}), 500


