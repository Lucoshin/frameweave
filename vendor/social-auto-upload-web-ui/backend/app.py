import asyncio
import hashlib
import hmac
import json
import os
import random
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path
from queue import Queue

import requests as _requests

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

BACKEND_DIR = Path(__file__).parent.resolve()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from conf import (
    BASE_DIR,
    FEEDBACK_API_BASE_URL,
    FEEDBACK_APP_KEY,
    FEEDBACK_APP_SECRET,
    FEEDBACK_API_TIMEOUT,
)
from util._logger import get_channel_logger
from services.account_operations import AccountBusyError, account_key, account_operations
from impl._browser import delete_account_profile

logger = get_channel_logger("backend")


def _ensure_materials_table():
    """服务启动时确保 materials 表存在"""
    DB_PATH = BASE_DIR / "db" / "database.db"
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id TEXT PRIMARY KEY,
            original_filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER DEFAULT 0,
            storage_type TEXT NOT NULL DEFAULT 'local',
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            duration REAL DEFAULT 0,
            thumbnail_path TEXT DEFAULT '',
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info("[Startup] materials 表已就绪")


_ensure_materials_table()

logger.info(f"[Startup] Python {sys.version} starting...")
logger.info(f"[Startup] Script: {__file__}")
logger.info(f"[Startup] SAU_PORT={os.environ.get('SAU_PORT')}, SAU_DATA_DIR={os.environ.get('SAU_DATA_DIR')}")
from impl.registry import get_platform
from impl.settings import read_settings
from services.login_sessions import LoginSessionManager, sse_stream

app = Flask(__name__)
CORS(app)
# 视频/图片上传不限大小（用户 2026-06-10 明确要求）
# 警告：当前 materials_bp.py:125 用 file.read() 一次性读入内存，超大文件会 OOM
# 如未来需要处理 ≥10GB 文件，应改为流式写入（request.stream → storage.save_stream）
app.config['MAX_CONTENT_LENGTH'] = None

login_sessions = LoginSessionManager()


def _is_terminal_import_sse_message(message: str) -> bool:
    if message in {"200", "500"}:
        return True
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        return False
    return str(payload.get("status", "")).lower() in {"200", "500", "0", "error"}


def import_sse_stream(status_queue):
    while True:
        if not status_queue.empty():
            msg = status_queue.get()
            yield f"data: {msg}\n\n"
            if _is_terminal_import_sse_message(msg):
                break
        else:
            time.sleep(0.1)


# 注册阶段二扩展 API Blueprint
logger.info("[Startup] Importing ext_api...")
from ext_api import ext_api  # noqa: E402
app.register_blueprint(ext_api)
logger.info("[Startup] ext_api registered OK")

from routes.frames import frames_bp  # noqa: E402
app.register_blueprint(frames_bp)
logger.info("[Startup] frames_bp registered OK")

from blueprints.image_publish_bp import image_publish_bp  # noqa: E402
app.register_blueprint(image_publish_bp)
logger.info("[Startup] image_publish_bp registered OK")

from blueprints.douyin_image_bp import douyin_image_bp  # noqa: E402
app.register_blueprint(douyin_image_bp)
logger.info("[Startup] douyin_image_bp registered OK")

from blueprints.toutiao_bp import toutiao_bp  # noqa: E402
app.register_blueprint(toutiao_bp)
logger.info("[Startup] toutiao_bp registered OK")

from blueprints.channels_bp import channels_bp  # noqa: E402
app.register_blueprint(channels_bp)
logger.info("[Startup] channels_bp registered OK")

from blueprints.weixin_gzh_bp import weixin_gzh_bp  # noqa: E402
app.register_blueprint(weixin_gzh_bp)
logger.info("[Startup] weixin_gzh_bp registered OK")

from blueprints.materials_bp import materials_bp  # noqa: E402
app.register_blueprint(materials_bp)
logger.info("[Startup] materials_bp registered OK")

from blueprints.uploads_bp import uploads_bp  # noqa: E402
app.register_blueprint(uploads_bp)
logger.info("[Startup] uploads_bp registered OK")

from blueprints.taobao_guanghe_bp import taobao_guanghe_bp  # noqa: E402
app.register_blueprint(taobao_guanghe_bp)
logger.info("[Startup] taobao_guanghe_bp registered OK")

from blueprints.jd_bp import bp as jd_bp  # noqa: E402
app.register_blueprint(jd_bp)
logger.info("[Startup] jd_picker registered OK")

from blueprints.word_generation_bp import word_generation_bp  # noqa: E402
app.register_blueprint(word_generation_bp)
logger.info("[Startup] word_generation_bp registered OK")

from blueprints.prepare_publish_bp import prepare_publish_bp  # noqa: E402
app.register_blueprint(prepare_publish_bp)
logger.info("[Startup] prepare_publish_bp registered OK")

from blueprints.animation_bp import animation_bp  # noqa: E402
app.register_blueprint(animation_bp)
logger.info("[Startup] animation_bp registered OK")

from blueprints.speech_bp import speech_bp  # noqa: E402
app.register_blueprint(speech_bp)
logger.info("[Startup] speech_bp registered OK")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
logger.info(f"[Startup] Frontend dir: {FRONTEND_DIR} (exists={FRONTEND_DIR.exists()})")


@app.route('/')
def index():
    if FRONTEND_DIR.exists():
        return send_from_directory(str(FRONTEND_DIR), 'index.html')
    return jsonify({"code": 200, "msg": "API server running"}), 200


@app.route('/assets/<path:filename>')
def custom_static(filename):
    return send_from_directory(str(FRONTEND_DIR / 'assets'), filename)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(str(FRONTEND_DIR), 'favicon.ico')


@app.route('/vite.svg')
def vite_svg():
    return send_from_directory(str(FRONTEND_DIR), 'vite.svg')


@app.route('/changelog/<path:filename>')
def serve_changelog(filename):
    changelog_dir = Path(__file__).parent.parent / "changelog"
    if not changelog_dir.exists():
        changelog_dir = BASE_DIR / "changelog"
    return send_from_directory(str(changelog_dir), filename)


# ── Helper ──────────────────────────────────────────────────

def _get_db_path():
    if data_dir := os.environ.get("SAU_DATA_DIR"):
        return Path(data_dir) / "db" / "database.db"
    return Path(__file__).parent.parent / "data" / "db" / "database.db"


DB_PATH = _get_db_path()
PLATFORM_MAP = {1: "小红书", 2: "视频号", 3: "抖音", 4: "快手", 5: "B站", 6: "百家号", 7: "TikTok", 8: "YouTube", 9: "腾讯视频", 10: "爱奇艺", 11: "微博", 12: "支付宝", 13: "今日头条", 14: "知乎", 15: "CSDN", 16: "VIVO", 17: "微信公众号", 18: "淘宝光合", 19: "京东京麦"}
PLATFORM_ID_TO_KEY = {
    1: 'xiaohongshu', 2: 'channels', 3: 'douyin', 4: 'kuaishou', 5: 'bilibili',
    6: 'baijiahao', 7: 'tiktok', 8: 'youtube', 9: 'tencent_video', 10: 'iqiyi',
    11: 'weibo', 12: 'alipay', 13: 'toutiao', 14: 'zhihu', 15: 'csdn', 16: 'vivo',
    17: 'weixin_gzh', 18: 'taobao_guanghe', 19: 'jingmai', 20: 'jd',
}


def _get_account_record(account_id):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user_info WHERE id = ?', (account_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# ── Account management ──────────────────────────────────────

@app.route("/getAccounts", methods=['GET'])
def getAccounts():
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_info')
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

            for row in rows_list:
                tags = conn.execute('''
                    SELECT t.id, t.name, t.color FROM tags t
                    JOIN account_tags at ON t.id = at.tag_id
                    WHERE at.account_id = ?
                ''', (row[0],)).fetchall()
                row.append([dict(t) for t in tags])

        return jsonify({"code": 200, "msg": None, "data": rows_list}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": f"获取账号列表失败: {str(e)}", "data": None}), 500


@app.route('/deleteAccount', methods=['GET'])
def delete_account():
    account_id = request.args.get('id')
    if not account_id or not account_id.isdigit():
        return jsonify({"code": 400, "msg": "Invalid or missing account ID", "data": None}), 400

    account_id = int(account_id)
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_info WHERE id = ?", (account_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({"code": 404, "msg": "account not found", "data": None}), 404

            record = dict(record)
            with account_operations.acquire([record['filePath']], "删除账号"):
                delete_account_profile(record['filePath'])
                cookie_file_path = Path(account_key(record['filePath']))
                if cookie_file_path.exists():
                    cookie_file_path.unlink()
                cursor.execute("DELETE FROM user_info WHERE id = ?", (account_id,))
                conn.commit()

        return jsonify({"code": 200, "msg": "account deleted successfully", "data": None}), 200
    except AccountBusyError:
        raise
    except Exception as e:
        return jsonify({"code": 500, "msg": f"delete failed: {str(e)}", "data": None}), 500


@app.route('/updateUserinfo', methods=['POST'])
def updateUserinfo():
    data = request.get_json()
    user_id = data.get('id')
    type_ = data.get('type')
    userName = data.get('userName')
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                'UPDATE user_info SET type = ?, userName = ? WHERE id = ?',
                (type_, userName, user_id)
            )
            conn.commit()
        return jsonify({"code": 200, "msg": "account update successfully", "data": None}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": "update failed!", "data": None}), 500


# ── Tag management ────────────────────────────────────────

@app.route('/api/tags', methods=['GET'])
def get_tags():
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM tags ORDER BY name').fetchall()
        return jsonify({"code": 200, "data": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/tags', methods=['POST'])
def create_tag():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    color = data.get('color') or random.choice([
        '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e',
        '#f97316', '#f59e0b', '#10b981', '#14b8a6',
        '#0ea5e9', '#3b82f6',
    ])
    if not name:
        return jsonify({"code": 400, "msg": "标签名不能为空"}), 400
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute('INSERT INTO tags (name, color) VALUES (?, ?)', (name, color))
            tag_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.commit()
        return jsonify({"code": 200, "data": {"id": tag_id, "name": name, "color": color}})
    except sqlite3.IntegrityError:
        return jsonify({"code": 409, "msg": "标签名已存在"}), 409
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            # SQLite 默认不强制外键,需要先清关联行
            conn.execute('DELETE FROM account_tags WHERE tag_id = ?', (tag_id,))
            conn.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
            conn.commit()
        return jsonify({"code": 200})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/accounts/<int:account_id>/tags', methods=['PUT'])
def set_account_tags(account_id):
    data = request.get_json()
    tag_ids = data.get('tag_ids', [])
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute('DELETE FROM account_tags WHERE account_id = ?', (account_id,))
            for tid in tag_ids:
                conn.execute('INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)', (account_id, tid))
            conn.commit()
        return jsonify({"code": 200})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/accounts/batch/tags', methods=['PUT'])
def set_batch_account_tags():
    """批量为多个账号添加相同的标签(追加模式:不清除已有标签)"""
    data = request.get_json()
    account_ids = data.get('account_ids', [])
    tag_ids = data.get('tag_ids', [])
    if not account_ids:
        return jsonify({"code": 400, "msg": "请选择至少一个账号"}), 400
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            for account_id in account_ids:
                for tid in tag_ids:
                    conn.execute('INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)', (account_id, tid))
            conn.commit()
        return jsonify({"code": 200, "data": {"updated": len(account_ids)}})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/accounts/<int:account_id>/tags', methods=['GET'])
def get_account_tags(account_id):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('''
                SELECT t.* FROM tags t
                JOIN account_tags at ON t.id = at.tag_id
                WHERE at.account_id = ?
                ORDER BY t.name
            ''', (account_id,)).fetchall()
        return jsonify({"code": 200, "data": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


# ── Cookie file management ──────────────────────────────────

@app.route('/uploadCookie', methods=['POST'])
def upload_cookie():
    try:
        if 'file' not in request.files:
            return jsonify({"code": 400, "msg": "没有找到Cookie文件", "data": None}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"code": 400, "msg": "Cookie文件名不能为空", "data": None}), 400
        if not file.filename.endswith('.json'):
            return jsonify({"code": 400, "msg": "Cookie文件必须是JSON格式", "data": None}), 400

        account_id = request.form.get('id')
        platform = request.form.get('platform')
        if not account_id or not platform:
            return jsonify({"code": 400, "msg": "缺少账号ID或平台信息", "data": None}), 400

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT filePath FROM user_info WHERE id = ?', (account_id,))
            result = cursor.fetchone()

        if not result:
            return jsonify({"code": 404, "msg": "账号不存在", "data": None}), 404

        with account_operations.acquire([result['filePath']], "更新登录文件"):
            cookie_file_path = Path(account_key(result['filePath']))
            cookie_file_path.parent.mkdir(parents=True, exist_ok=True)
            file.save(str(cookie_file_path))

        return jsonify({"code": 200, "msg": "Cookie文件上传成功", "data": None}), 200
    except AccountBusyError:
        raise
    except Exception as e:
        return jsonify({"code": 500, "msg": f"上传Cookie文件失败: {str(e)}", "data": None}), 500


@app.route('/downloadCookie', methods=['GET'])
def download_cookie():
    try:
        file_path = request.args.get('filePath')
        if not file_path:
            return jsonify({"code": 400, "msg": "缺少文件路径参数", "data": None}), 400

        cookie_file_path = Path(BASE_DIR / "cookiesFile" / file_path).resolve()
        base_path = Path(BASE_DIR / "cookiesFile").resolve()

        if not cookie_file_path.is_relative_to(base_path):
            return jsonify({"code": 400, "msg": "非法文件路径", "data": None}), 400
        if not cookie_file_path.exists():
            return jsonify({"code": 404, "msg": "Cookie文件不存在", "data": None}), 404

        return send_from_directory(
            directory=str(cookie_file_path.parent),
            path=cookie_file_path.name,
            as_attachment=True
        )
    except Exception as e:
        return jsonify({"code": 500, "msg": f"下载Cookie文件失败: {str(e)}", "data": None}), 500


# ── Core platform routes (new engine) ───────────────────────

@app.errorhandler(AccountBusyError)
def account_busy_error(exc):
    return jsonify({"code": 409, "msg": str(exc), "data": None}), 409


def _check_account_state(platform, cookie_file):
    with account_operations.acquire([cookie_file], "检查登录状态"):
        if not Path(account_key(cookie_file)).is_file():
            return "invalid", "账号登录文件不存在，请重新登录"
        try:
            valid = asyncio.run(platform.check_cookie(cookie_file))
        except (Exception, asyncio.CancelledError) as exc:
            logger.exception("账号登录状态检查失败")
            return "unknown", (str(exc) if isinstance(exc, asyncio.CancelledError) and str(exc)
                               else "未能确认登录状态，请检查网络或在账号窗口查看平台提示")
        if valid is True:
            return "valid", "登录状态有效"
        # 旧适配器把网络错误、验证页面与失效都压成 False，不能据此清空有效状态。
        return "unknown", "未能确认登录状态，请在账号窗口核实，暂不要求重新登录"


@app.route('/checkAccount', methods=['GET'])
def check_account():
    account_id = request.args.get('id')
    if not account_id or not account_id.isdigit():
        return jsonify({"code": 400, "msg": "无效的账号ID"}), 400

    record = _get_account_record(int(account_id))
    if not record:
        return jsonify({"code": 404, "msg": "账号不存在"}), 404

    platform = get_platform(record['type'])
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    state, message = _check_account_state(platform, record['filePath'])
    if state != "unknown":
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute('UPDATE user_info SET status = ? WHERE id = ?', (1 if state == "valid" else 0, record['id']))
    return jsonify({"code": 200, "msg": message, "data": {"id": record['id'], "status": state, "message": message}})


@app.route('/syncProfile', methods=['POST'])
def sync_profile():
    account_id = request.json.get('id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少账号ID", "data": None}), 400

    record = _get_account_record(account_id)
    if not record:
        return jsonify({"code": 404, "msg": "账号不存在", "data": None}), 404

    platform = get_platform(record['type'])
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型", "data": None}), 400

    # sync_profile 新约定:返回 dict{name, avatar, stats}
    # 兼容旧实现:返回 2 元组 (name, avatar) 时 stats 为 []
    with account_operations.acquire([record['filePath']], "同步账号资料"):
        try:
            result = asyncio.run(platform.sync_profile(record['filePath']))
        except asyncio.CancelledError as exc:
            return jsonify({"code": 409, "msg": str(exc) or "账号操作已停止，请检查平台页面", "data": None}), 409
    if isinstance(result, dict):
        name = result.get('name', '') or ''
        avatar = result.get('avatar', '') or ''
        stats = result.get('stats', []) or []
        if not isinstance(stats, list):
            stats = []
    elif isinstance(result, tuple):
        name = result[0] if len(result) > 0 else ''
        avatar = result[1] if len(result) > 1 else ''
        stats = []
    else:
        name, avatar, stats = '', '', []

    if not name and not avatar:
        return jsonify({"code": 502, "msg": "未能读取账号资料，原资料保持不变，请检查平台页面", "data": None}), 502

    if name or avatar:
        stats_json = json.dumps(stats, ensure_ascii=False)
        with sqlite3.connect(str(DB_PATH)) as conn:
            if name:
                conn.execute(
                    'UPDATE user_info SET userName = ?, avatar = ?, stats = ? WHERE id = ?',
                    (name, avatar, stats_json, account_id),
                )
            else:
                conn.execute(
                    'UPDATE user_info SET avatar = ?, stats = ? WHERE id = ?',
                    (avatar, stats_json, account_id),
                )

    return jsonify({
        "code": 200, "msg": "同步成功",
        "data": {"name": name, "avatar": avatar, "stats": stats},
    })


@app.route('/api/image-proxy')
def image_proxy():
    """头像代理：绕过 sinaimg.cn 防盗链。后端请求带 Referer=weibo.com。"""
    url = request.args.get('url')
    if not url:
        return jsonify({"code": 400, "msg": "缺少 url 参数"}), 400
    import httpx
    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/135.0.0.0 Safari/537.36",
                "Referer": "https://weibo.com/",
            },
            timeout=15,
        )
        return Response(resp.content, mimetype=resp.headers.get("content-type", "image/jpeg"))
    except Exception as e:
        logger.warning(f"[image-proxy] fetch failed: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/openCreatorCenter', methods=['POST'])
def open_creator_center():
    account_id = request.json.get('id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少账号ID"}), 400

    record = _get_account_record(account_id)
    if not record:
        return jsonify({"code": 404, "msg": "账号不存在"}), 404

    platform = get_platform(record['type'])
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    lease = account_operations.acquire([record['filePath']], "使用创作中心")

    def run_creator_center():
        try:
            asyncio.run(platform.open_creator_center(record['filePath']))
        except (Exception, asyncio.CancelledError):
            logger.exception("打开创作中心失败")
        finally:
            lease.close()

    try:
        thread = threading.Thread(target=run_creator_center, daemon=True)
        thread.start()
    except BaseException:
        lease.close()
        raise
    return jsonify({"code": 200, "msg": "正在打开创作中心"})


@app.route('/login')
def login():
    type_str = request.args.get('type')
    id_str = request.args.get('id')
    account_id = request.args.get('account_id')
    if not type_str or not id_str:
        return jsonify({"code": 400, "msg": "缺少 type 或 id"}), 400

    try:
        platform_type = int(type_str)
    except (TypeError, ValueError):
        return jsonify({"code": 400, "msg": "type 必须是整数"}), 400

    platform = get_platform(platform_type)
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    cookie_file = None
    if account_id is not None:
        record = _get_account_record(account_id)
        if record is None or record['type'] != platform_type:
            return jsonify({"code": 400, "msg": "账号不存在或不属于所选平台"}), 400
        cookie_file = record['filePath']
    busy_event = None
    try:
        session = login_sessions.start(id_str, platform, account_id=account_id, cookie_file=cookie_file)
    except AccountBusyError as exc:
        # EventSource 无法读取 HTTP 409 JSON 正文；登录沿用终态 SSE 错误，展示实际占用原因。
        session = None
        busy_event = {"status": "error", "code": "ACCOUNT_BUSY", "msg": str(exc)}
    if session is None:
        status_queue = Queue()
        status_queue.put(busy_event or {
            "status": "error",
            "code": "LOGIN_BUSY",
            "msg": "已有登录任务正在进行，请先完成或取消",
        })
        stream = sse_stream(status_queue)
    else:
        stream = sse_stream(
            session.events,
            on_disconnect=lambda: login_sessions.cancel(id_str),
        )

    response = Response(stream, mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Content-Type'] = 'text/event-stream'
    return response


@app.route('/api/login-sessions/<session_id>/cancel', methods=['POST'])
def cancel_login_session(session_id):
    if not login_sessions.cancel(session_id):
        return jsonify({
            "code": "LOGIN_SESSION_NOT_FOUND",
            "msg": "登录任务不存在或已结束",
        }), 404
    return jsonify({
        "code": "LOGIN_CANCEL_REQUESTED",
        "msg": "已请求取消登录",
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Cookie 导入账号
# ─────────────────────────────────────────────────────────────────────────────

# 导入任务的 task_id → status_queue；与 /login 共用 SSE 协议
import_active_queues: dict[str, Queue] = {}


@app.route('/platforms/import-supported', methods=['GET'])
def platforms_import_supported():
    """列出所有支持 cookie 字符串导入的平台。

    返回精简字段，前端用来渲染「导入用户」弹窗的平台选择下拉。
    """
    from impl.registry import get_platform
    out = []
    for pid in sorted(PLATFORM_MAP.keys()):
        p = get_platform(pid)
        if p is None or not getattr(p, "supports_cookie_import", False):
            continue
        out.append({
            "id": pid,
            "key": p.platform_key,
            "name": p.platform_name,
            "letter": (p.platform_name[:1] if p.platform_name else ""),
        })
    return jsonify({"code": 200, "msg": "ok", "data": out}), 200


@app.route('/importAccount', methods=['POST'])
def import_account_start():
    """启动一个 cookie 导入任务。

    Request body (JSON):
        type:        platform_id (int)
        cookie_str:  浏览器导出的 'k=v; k=v' 字符串
        account_id:  可选；已存在账号的 id（re-import 时更新 cookie 文件）

    Response:
        {"code": 200, "msg": "ok", "data": {"task_id": "..."}}

    前端拿到 task_id 后再 EventSource('/importAccount/stream?task_id=...') 拉进度。
    """
    data = request.get_json(silent=True) or {}
    type_raw = data.get('type')
    cookie_str = (data.get('cookie_str') or '').strip()
    account_id_raw = data.get('account_id')

    if type_raw is None or not cookie_str:
        return jsonify({
            "code": 400, "msg": "缺少 type 或 cookie_str", "data": None,
        }), 400

    try:
        type_int = int(type_raw)
    except (TypeError, ValueError):
        return jsonify({
            "code": 400, "msg": "type 必须是整数", "data": None,
        }), 400

    platform = get_platform(type_int)
    if platform is None:
        return jsonify({
            "code": 400, "msg": "不支持的平台", "data": None,
        }), 400
    if not getattr(platform, "supports_cookie_import", False):
        return jsonify({
            "code": 400, "msg": f"{platform.platform_name} 暂不支持 cookie 导入",
            "data": None,
        }), 400

    account_id = None
    if account_id_raw is not None and str(account_id_raw).strip():
        try:
            account_id = int(account_id_raw)
        except (TypeError, ValueError):
            return jsonify({
                "code": 400, "msg": "account_id 必须是整数", "data": None,
            }), 400

    cookie_files = []
    if account_id is not None:
        record = _get_account_record(account_id)
        if record is None or record['type'] != type_int:
            return jsonify({"code": 400, "msg": "账号不存在或不属于所选平台", "data": None}), 400
        cookie_files.append(record['filePath'])
    lease = account_operations.acquire(cookie_files, "导入登录状态")
    task_id = uuid.uuid4().hex
    status_queue: Queue = Queue()
    import_active_queues[task_id] = status_queue

    def _cleanup():
        import_active_queues.pop(task_id, None)

    def _run_import():
        try:
            asyncio.run(platform.import_cookie(
                cookie_str, status_queue, account_id=account_id,
            ))
        except asyncio.CancelledError:
            status_queue.put(json.dumps({
                "status": "error", "step": 0, "msg": "任务被取消",
            }))
        except Exception as e:
            # import_cookie 内部已经把 error 推过 queue 了；这里是兜底
            logger.info(f"[importAccount] 未捕获异常: {e}")
            try:
                status_queue.put(json.dumps({
                    "status": "error", "step": 0, "msg": str(e),
                }))
            except Exception:
                pass

        finally:
            lease.close()

    try:
        thread = threading.Thread(target=_run_import, daemon=True)
        thread.start()
    except BaseException:
        lease.close()
        _cleanup()
        raise

    return jsonify({
        "code": 200, "msg": "ok",
        "data": {"task_id": task_id},
    }), 200


@app.route('/importAccount/stream', methods=['GET'])
def import_account_stream():
    """SSE 推送 cookie 导入进度。"""
    task_id = request.args.get('task_id')
    if not task_id or task_id not in import_active_queues:
        return jsonify({
            "code": 404, "msg": "task 不存在或已结束", "data": None,
        }), 404

    status_queue = import_active_queues[task_id]

    def _cleanup():
        import_active_queues.pop(task_id, None)

    response = Response(
        import_sse_stream(status_queue), mimetype='text/event-stream',
    )
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Content-Type'] = 'text/event-stream'
    response.call_on_close(_cleanup)
    return response


@app.before_request
def _ensure_db():
    db_path = _get_db_path()
    need_init = False
    if not db_path.exists():
        need_init = True
    else:
        try:
            with sqlite3.connect(str(db_path)) as _c:
                _c.execute("SELECT 1 FROM user_info LIMIT 1")
        except sqlite3.OperationalError:
            need_init = True
    if need_init:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from init_db import init_database, migrate_database
            init_database()
            migrate_database()
            logger.info(f"[DB] Initialized database at {db_path}")
        except Exception as e:
            logger.info(f"[DB] Failed to initialize database: {e}")


# ── Health / diagnostics ────────────────────────────────────

@app.route("/api/health", methods=['GET'])
def health_check():
    import sqlite3 as _sqlite
    diag = {
        "sau_data_dir": os.environ.get("SAU_DATA_DIR"),
        "base_dir": str(BASE_DIR),
        "db_path": str(_get_db_path()),
        "db_exists": _get_db_path().exists(),
        "python": sys.executable,
        "sys_prefix": sys.prefix,
        "sys_base_prefix": sys.base_prefix,
    }
    try:
        with _sqlite.connect(str(_get_db_path())) as _conn:
            count = _conn.execute("SELECT COUNT(*) FROM user_info").fetchone()[0]
            diag["db_user_count"] = count
            diag["db_ok"] = True
    except Exception as e:
        diag["db_ok"] = False
        diag["db_error"] = str(e)
    return jsonify(diag)


# ── 反馈系统代理（HMAC 签名由后端完成，前端永不接触 app_secret）──


def _feedback_sign(timestamp_ms: str, app_key: str = None, app_secret: str = None) -> str:
    if app_key is None:
        app_key = FEEDBACK_APP_KEY
    if app_secret is None:
        app_secret = FEEDBACK_APP_SECRET
    msg = f"{app_key}{timestamp_ms}{app_secret}".encode('utf-8')
    return hmac.new(app_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()


def _feedback_headers() -> dict:
    """生成带 HMAC 签名的反馈系统请求头。"""
    ts = str(int(time.time() * 1000))
    return {
        'X-App-Key': FEEDBACK_APP_KEY,
        'X-Timestamp': ts,
        'X-Sign': _feedback_sign(ts),
    }


def _get_feedback_email() -> str:
    """从 settings 表读 feedbackEmail（用户全局邮箱）。空字符串表示未配置。"""
    val = read_settings().get('feedbackEmail')
    return (val or '').strip() if isinstance(val, str) else ''


@app.route('/api/feedback/list', methods=['GET'])
def feedback_list():
    """状态筛选：全部 / 待确认 / 处理中 / 已完成 / 已拒绝
    - 不传 status + 不传 include_all → 仅 status 1+2（默认）
    - status=1/2/3/4 → 仅对应状态
    - include_all=true → 全部
    """
    try:
        page = int(request.args.get('page', 1))
        page_size = min(int(request.args.get('page_size', 20)), 100)
    except ValueError:
        return jsonify({'code': 400, 'message': 'page / page_size 必须是整数', 'data': None}), 400

    status_str = request.args.get('status', '').strip()
    include_all = request.args.get('include_all', '').lower() == 'true'

    params = {'page': page, 'page_size': page_size}
    if status_str:
        try:
            params['status'] = int(status_str)
        except ValueError:
            return jsonify({'code': 400, 'message': 'status 必须是整数 (1-4)', 'data': None}), 400
    elif include_all:
        params['include_all'] = 'true'

    # 从 settings 表读用户邮箱，作为 metoo 计算依据
    viewer_email = _get_feedback_email()
    if viewer_email:
        params['email'] = viewer_email

    try:
        r = _requests.get(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback",
            params=params,
            headers=_feedback_headers(),
            timeout=FEEDBACK_API_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502

    # attachment.file_url 从相对路径改写为绝对 URL
    for item in data.get('data', {}).get('list', []):
        for att in item.get('attachments') or []:
            if att.get('file_url', '').startswith('/'):
                att['file_url'] = FEEDBACK_API_BASE_URL + att['file_url']

    return jsonify(data)


@app.route('/api/feedback/submit', methods=['POST'])
def feedback_submit():
    content = request.form.get('content', '').strip()
    # 邮箱优先取表单（覆盖场景），否则从 settings 读
    email = request.form.get('email', '').strip() or _get_feedback_email()
    if not email or not content:
        return jsonify({'code': 400, 'message': '邮箱和内容必填；如未配置邮箱请先在设置页填写', 'data': None}), 400

    files = []
    for f in request.files.getlist('files'):
        files.append(('files', (f.filename, f.stream, f.mimetype)))

    try:
        r = _requests.post(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback",
            data={'email': email, 'content': content},
            files=files,
            headers=_feedback_headers(),
            timeout=FEEDBACK_API_TIMEOUT,
        )
        return (r.json(), r.status_code)
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502


@app.route('/api/feedback/vote', methods=['POST'])
def feedback_vote():
    body = request.get_json(silent=True) or {}
    fb_id = body.get('id')
    # 邮箱优先取 body（允许前端临时用别的身份），否则从 settings 读
    email = (body.get('email') or '').strip() or _get_feedback_email()
    if not fb_id or not email:
        return jsonify({'code': 400, 'message': 'id 和 email 必填；如未配置邮箱请先在设置页填写', 'data': None}), 400

    try:
        r = _requests.post(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback/{fb_id}/vote",
            json={'email': email},
            headers=_feedback_headers(),
            timeout=FEEDBACK_API_TIMEOUT,
        )
        return (r.json(), r.status_code)
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502


# ── Server entry ────────────────────────────────────────────

def find_available_port(start_port=5409, max_attempts=10):
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find available port in range {start_port}-{start_port + max_attempts}")


if __name__ == "__main__":
    import socket

    logger.info("[Startup] Initializing database...")
    from init_db import init_database, migrate_database
    init_database()
    migrate_database()
    logger.info("[Startup] Database initialized OK")

    try:
        import sqlite3 as _sqlite
        _test_path = _get_db_path()
        logger.info(f"[Startup] DB path: {_test_path} (exists={_test_path.exists()})")
        with _sqlite.connect(str(_test_path)) as _conn:
            _conn.execute("SELECT 1 FROM user_info LIMIT 1")
        logger.info("[Startup] DB verification OK")
    except Exception as _e:
        logger.info(f"[Startup] DB verification FAILED: {_e}")
        logger.info(f"[Startup] SAU_DATA_DIR={os.environ.get('SAU_DATA_DIR')}")

    # 启动后台任务：补全存量视频素材 duration=0 的数据，以及缺失 orientation 的数据
    # （草稿/历史恢复走 DB 直读，绕过了「素材库选中→probe」，
    #  导致历史 duration=0 的数据漏识别，发布校验被跳过）
    try:
        from services.duration_repair import start_repair_in_background
        start_repair_in_background()
    except Exception as _e:
        logger.warning("[Startup] 补全任务启动失败（不影响主服务）: %s", _e)

    # 账号登录状态检查机制:如果设置为「启动时检测」,后台异步检测所有账号 cookie
    try:
        _check_mode = "manual"
        try:
            with _sqlite.connect(str(_get_db_path())) as _c:
                _row = _c.execute("SELECT value FROM settings WHERE key='accountCheckMode'").fetchone()
                if _row:
                    _check_mode = _row[0]
        except Exception:
            pass
        if _check_mode == "startup":
            logger.info("[Startup] 账号检查模式=启动时检测,开始后台异步检测所有账号...")
            import threading as _threading

            def _check_all_accounts():
                import sqlite3 as _sqlite
                try:
                    db_path = _get_db_path()
                    with _sqlite.connect(str(db_path)) as conn:
                        rows = conn.execute(
                            "SELECT id, type, filePath, userName FROM user_info"
                        ).fetchall()
                    logger.info(f"[Startup] 共 {len(rows)} 个账号待检测")
                    from impl.registry import get_platform
                    for row in rows:
                        acc_id, acc_type, cookie_file, nick = row
                        try:
                            platform = get_platform(acc_type)
                            if not platform:
                                continue
                            state, message = _check_account_state(platform, cookie_file)
                            if state == "unknown":
                                logger.info("[Startup] 账号 %s 检查未确认，保留原状态: %s", acc_id, message)
                                continue
                            new_status = 1 if state == "valid" else 0
                            with _sqlite.connect(str(db_path)) as conn:
                                conn.execute(
                                    "UPDATE user_info SET status=? WHERE id=?",
                                    (new_status, acc_id),
                                )
                                conn.commit()
                            logger.info(f"[Startup] 账号 {nick}(id={acc_id}) 检测完成: {state}")
                        except Exception as e:
                            logger.info(f"[Startup] 账号 {nick}(id={acc_id}) 检测异常: {e}")
                    logger.info("[Startup] 所有账号检测完成")
                except Exception as e:
                    logger.info(f"[Startup] 账号检测线程异常: {e}")

            _t = _threading.Thread(target=_check_all_accounts, daemon=True)
            _t.start()
            logger.info("[Startup] 账号检测后台线程已启动")
        else:
            logger.info("[Startup] 账号检查模式=仅手动检查,跳过启动时检测")
    except Exception as _e:
        logger.warning("[Startup] 账号检查模式读取失败（不影响主服务）: %s", _e)

    port = int(os.environ.get("SAU_PORT", "5409"))
    if port == 5409:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
        except OSError:
            port = find_available_port(5409 + 1)
            logger.info(f"[Startup] Port 5409 in use, using port {port}")
    logger.info(f"[Startup] Starting Waitress server on port {port}")
    from waitress import serve
    os.environ["SAU_PORT"] = str(port)
    # threads=16：默认 4 线程会被「并发 checkCookie + 多个 SSE /login 长连接」
    # 占满，导致后端假死。加大线程池让两者不再互相挤占。
    serve(app, host="0.0.0.0", port=port, threads=16)
