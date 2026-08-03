"""代理节点健康扫描任务。"""
import asyncio

from loguru import logger

from app.core.config import get_settings
from app.core.database import get_db_context
from app.services.agent_service import agent_service


async def scan_agents_loop(stop_event: asyncio.Event) -> None:
    """定时扫描代理节点健康状态。

    使用 stop_event 作为停止信号，便于在应用关闭时优雅退出。
    """
    settings = get_settings()
    interval = max(1, settings.agent_scan_interval_seconds)
    logger.info("代理健康扫描已启动，间隔 {} 秒", interval)

    while not stop_event.is_set():
        try:
            async with get_db_context() as db:
                agents = await agent_service.list_online(db)
                logger.debug("健康扫描开始，在线候选数={}", len(agents))
                for agent in agents:
                    is_online = await agent_service.check_health(agent)
                    await agent_service.update_status(db, agent, is_online=is_online)
                logger.debug("健康扫描结束")
        except Exception as exc:
            logger.error("代理健康扫描异常: {}", exc)

        try:
            logger.debug("健康扫描等待 {} 秒", interval)
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            # 超时是正常的下一轮扫描信号，不需要打印堆栈
            continue
        except asyncio.CancelledError:
            logger.info("代理健康扫描任务已取消")
            break
