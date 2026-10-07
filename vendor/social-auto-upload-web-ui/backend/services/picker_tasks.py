"""选择面板的跨线程调用：超时取消和资源清理始终在所属事件循环完成。"""

import asyncio


def run_picker_task(loop, coroutine, *, timeout, cleanup=None, session=None):
    async def run():
        task = asyncio.create_task(coroutine)
        if session is not None:
            session._picker_tasks.add(task)
        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except BaseException as exc:
            if cleanup is not None:
                await asyncio.wait_for(cleanup(), timeout=10)
            if isinstance(exc, TimeoutError):
                raise TimeoutError("选择面板操作超时，已停止当前操作，请重新打开面板") from exc
            raise
        finally:
            if session is not None:
                session._picker_tasks.discard(task)

    # 超时由事件循环内的 wait_for 控制。Future.result(timeout)只停止HTTP等待，
    # 不会取消浏览器操作；因此必须等协程取消及清理结束后才能向调用方返回。
    return asyncio.run_coroutine_threadsafe(run(), loop).result()
