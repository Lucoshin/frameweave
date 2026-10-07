"""
抖音图文发布相关API代理
使用CloakBrowser来请求抖音API，避免反检测
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("douyin_image")

douyin_image_bp = Blueprint('douyin_image', __name__, url_prefix='/api/douyin-image')


def _get_cookie_path(cookie_file: str) -> str:
    """获取cookie文件的完整路径"""
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str:
    """从数据库获取账号的cookie文件路径"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        cursor.execute("SELECT filePath FROM user_info WHERE type = 3 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


async def _fetch_with_browser(cookie_file: str, url: str, base_url: str = "https://creator.douyin.com/") -> dict:
    """使用CloakBrowser发送GET请求"""
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True, storage_state=cookie_path)
    try:
        context = await create_context(browser)
        try:
            page = await context.new_page()

            # 先打开基础URL，确保cookie生效
            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # 使用fetch API请求目标URL
            escaped_url = url.replace("'", "\\'").replace('"', '\\"')

            # 根据URL域名设置Referer
            referer = base_url
            if "tsearch.amemv.com" in url:
                referer = "https://creator.douyin.com/"

            result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const response = await fetch("{escaped_url}", {{
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/json',
                                'Referer': '{referer}',
                            }}
                        }});

                        // 先获取文本，再尝试解析JSON
                        const text = await response.text();

                        if (!response.ok) {{
                            return {{ success: false, error: `HTTP ${{response.status}}: ${{text.substring(0, 200)}}` }};
                        }}

                        try {{
                            const data = JSON.parse(text);
                            return {{ success: true, data: data }};
                        }} catch (jsonError) {{
                            return {{ success: false, error: `JSON解析失败: ${{jsonError.message}}, 响应内容: ${{text.substring(0, 200)}}` }};
                        }}
                    }} catch (e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }}
            """)

            return result
        finally:
            await context.close()
    finally:
        await browser.close()


async def _fetch_with_browser_post(cookie_file: str, url: str, form_data: dict, base_url: str = "https://creator.douyin.com/") -> dict:
    """使用CloakBrowser发送POST请求"""
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True, storage_state=cookie_path)
    try:
        context = await create_context(browser)
        try:
            page = await context.new_page()

            # 先打开基础URL，确保cookie生效
            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # 使用fetch API发送POST请求
            escaped_url = url.replace("'", "\\'").replace('"', '\\"')

            # 将form_data转为JSON字符串
            import json
            form_data_json = json.dumps(form_data)

            result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const response = await fetch("{escaped_url}", {{
                            method: 'POST',
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/json',
                                'Content-Type': 'application/x-www-form-urlencoded',
                                'Referer': 'https://creator.douyin.com/',
                            }},
                            body: new URLSearchParams({form_data_json})
                        }});

                        // 先获取文本，再尝试解析JSON
                        const text = await response.text();

                        if (!response.ok) {{
                            return {{ success: false, error: `HTTP ${{response.status}}: ${{text.substring(0, 200)}}` }};
                        }}

                        try {{
                            const data = JSON.parse(text);
                            return {{ success: true, data: data }};
                        }} catch (jsonError) {{
                            return {{ success: false, error: `JSON解析失败: ${{jsonError.message}}, 响应内容: ${{text.substring(0, 200)}}` }};
                        }}
                    }} catch (e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }}
            """)

            return result
        finally:
            await context.close()
    finally:
        await browser.close()


def run_async(coro):
    """Flask 同步请求边界：浏览器取消必须变成明确错误，不能丢在线程中。"""
    try:
        return asyncio.run(coro)
    except asyncio.CancelledError as exc:
        raise RuntimeError(str(exc) or "账号操作已停止，请检查平台页面") from exc


@douyin_image_bp.route('/mix-list', methods=['GET'])
def get_mix_list():
    """获取用户的合集列表"""
    account_id = request.args.get('account_id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少account_id参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "账号不存在"}), 404

        url = "https://creator.douyin.com/web/api/mix/list/?status=0%2C2&count=15&cursor=0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+%28Windows+NT+10.0%3B+Win64%3B+x64%29+AppleWebKit%2F537.36+%28KHTML%2C+like+Gecko%29+Chrome%2F146.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&aid=1128&support_h265=0"
        result = run_async(_fetch_with_browser(cookie_file, url))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"获取合集列表失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/activity-list', methods=['GET'])
def get_activity_list():
    """获取官方活动列表"""
    account_id = request.args.get('account_id')

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        url = "https://creator.douyin.com/web/api/media/activity/get/?page=1&size=9999&need_challenge=1&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+%28Windows+NT+10.0%3B+Win64%3B+x64%29+AppleWebKit%2F537.36+%28KHTML%2C+like+Gecko%29+Chrome%2F146.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&aid=1128&support_h265=0"
        result = run_async(_fetch_with_browser(cookie_file, url))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"获取活动列表失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/hotspot-search', methods=['GET'])
def search_hotspot():
    """搜索热点"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    count = request.args.get('count', '50')

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        url = f"https://creator.douyin.com/aweme/v1/hotspot/search/?query={quote(keyword)}&count={count}&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+%28Windows+NT+10.0%3B+Win64%3B+x64%29+AppleWebKit%2F537.36+%28KHTML%2C+like+Gecko%29+Chrome%2F146.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&aid=1128&support_h265=0"
        result = run_async(_fetch_with_browser(cookie_file, url))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"搜索热点失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/search-poi', methods=['GET'])
def search_poi():
    """搜索位置"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    count = request.args.get('count', '12')

    logger.info(f"[位置搜索] 收到请求: account_id={account_id}, keyword={keyword}")

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        url = f"https://creator.douyin.com/aweme/v1/life/video_api/search/poi/?count={count}&from_webapp=1&get_current_loc=1&is_image_album_style=1&keywords={quote(keyword)}&search_type=0&poi_anchor_tab=2&page=1&poi_mode=2&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+%28Windows+NT+10.0%3B+Win64%3B+x64%29+AppleWebKit%2F537.36+%28KHTML%2C+like+Gecko%29+Chrome%2F146.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&aid=1128&support_h265=0"
        result = run_async(_fetch_with_browser(cookie_file, url))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"搜索位置失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/search-miniapp', methods=['GET'])
def search_miniapp():
    """搜索小程序 - 通过链接查询"""
    account_id = request.args.get('account_id')
    link = request.args.get('link', '')

    logger.info(f"[小程序搜索] 收到请求: account_id={account_id}, link={link}")

    if not link:
        return jsonify({"code": 400, "msg": "缺少link参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        # 小程序搜索是POST请求，使用form data，带上浏览器指纹信息
        url = ("https://creator.douyin.com/web/api/media/anchor/search/?"
               "cookie_enabled=true&screen_width=1920&screen_height=1080&"
               "browser_language=zh-CN&browser_platform=Win32&"
               "browser_name=Mozilla&browser_version=5.0+%28Windows+NT+10.0%3B+Win64%3B+x64%29+AppleWebKit%2F537.36+%28KHTML%2C+like+Gecko%29+Chrome%2F146.0.0.0+Safari%2F537.36&"
               "browser_online=true&timezone_name=Asia%2FShanghai&"
               "aid=1128&support_h265=0")
        form_data = {
            "keyword": link,
            "anchor_type": "4"
        }
        logger.info(f"[小程序搜索] 请求URL: {url}")
        logger.info(f"[小程序搜索] form_data: {form_data}")
        result = run_async(_fetch_with_browser_post(cookie_file, url, form_data))
        logger.info(f"[小程序搜索] 返回结果: success={result.get('success')}")
        if result.get("success"):
            data = result["data"]
            logger.info(f"[小程序搜索] 返回数据: status_code={data.get('status_code')}, anchor_list数量={len(data.get('anchor_list', []))}")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[小程序搜索] 请求失败: {result.get('error')}")
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"搜索小程序失败: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/search-game', methods=['GET'])
def search_game():
    """搜索游戏"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    count = request.args.get('count', '20')

    logger.info(f"[游戏搜索] 收到请求: account_id={account_id}, keyword={keyword}")

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        # 游戏搜索使用 game_name 参数
        url = f"https://creator.douyin.com/webcast/gamecp/mount_page/search?game_name={quote(keyword)}&count={count}&scene=3&version_code=24.0.0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+%28Windows+NT+10.0%3B+Win64%3B+x64%29+AppleWebKit%2F537.36+%28KHTML%2C+like+Gecko%29+Chrome%2F146.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&aid=2906&support_h265=0"
        logger.info(f"[游戏搜索] 请求URL: {url}")
        result = run_async(_fetch_with_browser(cookie_file, url))
        logger.info(f"[游戏搜索] 返回结果: success={result.get('success')}")
        if result.get("success"):
            data = result["data"]
            logger.info(f"[游戏搜索] 返回数据: status_code={data.get('status_code')}, mount_games数量={len(data.get('data', {}).get('mount_games', []))}")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[游戏搜索] 请求失败: {result.get('error')}")
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"搜索游戏失败: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/search-mark-spu', methods=['GET'])
def search_mark_spu():
    """搜索标记万物商品"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    page_size = request.args.get('page_size', '10')

    logger.info(f"[标记万物搜索] 收到请求: account_id={account_id}, keyword={keyword}")

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        # 标记万物搜索使用 query_word 参数
        url = f"https://creator.douyin.com/web/api/media/aweme/mark_anchor/spu_list?query_word={quote(keyword)}&page_size={page_size}&page=0&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+%28Windows+NT+10.0%3B+Win64%3B+x64%29+AppleWebKit%2F537.36+%28KHTML%2C+like+Gecko%29+Chrome%2F146.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&aid=1128&support_h265=0"
        logger.info(f"[标记万物搜索] 请求URL: {url}")
        result = run_async(_fetch_with_browser(cookie_file, url))
        logger.info(f"[标记万物搜索] 返回结果: success={result.get('success')}")
        if result.get("success"):
            data = result["data"]
            logger.info(f"[标记万物搜索] 返回数据: status_code={data.get('status_code')}, spu_list数量={len(data.get('data', {}).get('spu_list', []))}")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[标记万物搜索] 请求失败: {result.get('error')}")
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500
    except Exception as e:
        logger.error(f"搜索标记万物失败: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/search-medium', methods=['GET'])
def search_medium():
    """搜索影视演绎"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    count = request.args.get('count', '12')
    offset = request.args.get('offset', '0')

    logger.info(f"[影视演绎搜索] 收到请求: account_id={account_id}, keyword={keyword}")

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        url = f"https://creator.douyin.com/web/api/medium/search/?count={count}&keyword={quote(keyword)}&offset={offset}&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN&browser_platform=Win32&browser_name=Mozilla&browser_version=5.0+%28Windows+NT+10.0%3B+Win64%3B+x64%29+AppleWebKit%2F537.36+%28KHTML%2C+like+Gecko%29+Chrome%2F146.0.0.0+Safari%2F537.36&browser_online=true&timezone_name=Asia%2FShanghai&aid=1128&support_h265=0"
        logger.info(f"[影视演绎搜索] 请求URL: {url}")
        result = run_async(_fetch_with_browser(cookie_file, url))
        logger.info(f"[影视演绎搜索] 返回结果: success={result.get('success')}")
        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            logger.error(f"[影视演绎搜索] 请求失败: {result.get('error')}")
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"[影视演绎搜索] 异常: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500
