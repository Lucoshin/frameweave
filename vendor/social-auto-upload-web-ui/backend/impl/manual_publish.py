from urllib.parse import urlsplit


def final_submit_allowed(*, prepare_only: bool, legacy_dry_run: bool) -> bool:
    """最终发布点击的单一安全判定。

    ``prepare_only`` 是半自动 API 每个任务强制传入的安全标记；
    它的优先级高于上游保留的全局 dry-run 开关。
    """
    return not prepare_only and not legacy_dry_run


async def submit_and_confirm(page, platform, submit, *, on_submitting=None, on_confirmed=None):
    """每份稿件只点击一次；明确的平台成功信号才可回报已提交。

    超时不能证明提交失败，重复点击可能重复投稿，因此停止并提示人工核实。
    「已提交」只表示平台接收，不等于审核通过或已经公开展示。
    """
    if platform == "bilibili" and await page.get_by_text("稿件投递成功", exact=True).is_visible():
        raise RuntimeError("提交前已存在成功提示，无法区分本次结果，请人工确认")
    if callable(on_submitting):
        on_submitting()
    await submit()
    try:
        if platform == "bilibili":
            await page.get_by_text("稿件投递成功", exact=True).wait_for(state="visible", timeout=60000)
            if urlsplit(page.url).hostname != "member.bilibili.com":
                raise RuntimeError("页面已离开创作中心")
            signal = f"{page.url} · 稿件投递成功"
        else:
            target = {
                "douyin": "https://creator.douyin.com/creator-micro/content/manage**",
                "xiaohongshu": "https://creator.xiaohongshu.com/publish/success**",
            }[platform]
            await page.wait_for_url(target, timeout=60000)
            signal = page.url
    except Exception as exc:
        raise RuntimeError("未确认平台提交结果，请先到创作中心核实，避免重复发布") from exc
    if callable(on_confirmed):
        on_confirmed(signal)
