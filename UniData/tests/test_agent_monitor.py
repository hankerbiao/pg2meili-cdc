"""agent_monitor 单元测试（无需 DB / 真实 Redis）。

mock 掉 get_db_context 与 agent_service，验证扫描循环：
- 正常轮次会 list_online -> check_health -> update_status；
- 单轮扫描异常被吞掉（记录日志，不抛出）；
- 一轮扫描结束后（interval 到达）循环退出。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import agent_monitor


@asynccontextmanager
async def _fake_db_ctx():
    yield SimpleNamespace()


def _agent(itcode: str, online: bool) -> SimpleNamespace:
    return SimpleNamespace(itcode=itcode, is_online=online)


def _fake_wait_that_stops(stop: asyncio.Event):
    """模拟一轮 interval 等待：置位 stop 并抛 TimeoutError，使循环恰好跑一轮后退出。"""

    async def _wait(coro, timeout=None):
        stop.set()
        raise asyncio.TimeoutError()

    return _wait


async def test_scan_iteration_checks_and_updates_per_agent():
    agents = [_agent("a1", True), _agent("a2", False)]
    svc = SimpleNamespace(
        list_online=AsyncMock(return_value=agents),
        check_health=AsyncMock(return_value=True),
        update_status=AsyncMock(),
    )
    stop = asyncio.Event()
    with patch.object(agent_monitor, "get_db_context", _fake_db_ctx), patch.object(
        agent_monitor, "agent_service", svc
    ), patch.object(agent_monitor, "get_settings", lambda: SimpleNamespace(agent_scan_interval_seconds=1)), patch(
        "app.services.agent_monitor.logger"
    ), patch.object(agent_monitor.asyncio, "wait_for", side_effect=_fake_wait_that_stops(stop)):
        await agent_monitor.scan_agents_loop(stop)

    svc.list_online.assert_awaited_once()
    assert svc.check_health.await_count == 2
    assert svc.update_status.await_count == 2
    for call in svc.update_status.await_args_list:
        assert call.kwargs["is_online"] is True  # check_health mock 恒 True


async def test_scan_swallows_agent_error_and_continues():
    agents = [_agent("a1", True)]

    async def _boom(agent):
        raise RuntimeError("health down")

    svc = SimpleNamespace(
        list_online=AsyncMock(return_value=agents),
        check_health=_boom,
        update_status=AsyncMock(),
    )
    stop = asyncio.Event()
    with patch.object(agent_monitor, "get_db_context", _fake_db_ctx), patch.object(
        agent_monitor, "agent_service", svc
    ), patch.object(agent_monitor, "get_settings", lambda: SimpleNamespace(agent_scan_interval_seconds=1)), patch(
        "app.services.agent_monitor.logger"
    ), patch.object(agent_monitor.asyncio, "wait_for", side_effect=_fake_wait_that_stops(stop)):
        # 不应向外抛出
        await agent_monitor.scan_agents_loop(stop)

    # 异常被吞，update_status 不被调用
    svc.update_status.assert_not_awaited()


async def test_scan_runs_exactly_one_round_when_stopped():
    svc = SimpleNamespace(
        list_online=AsyncMock(return_value=[]),
        check_health=AsyncMock(),
        update_status=AsyncMock(),
    )
    stop = asyncio.Event()
    with patch.object(agent_monitor, "get_db_context", _fake_db_ctx), patch.object(
        agent_monitor, "agent_service", svc
    ), patch.object(agent_monitor, "get_settings", lambda: SimpleNamespace(agent_scan_interval_seconds=1)), patch(
        "app.services.agent_monitor.logger"
    ), patch.object(agent_monitor.asyncio, "wait_for", side_effect=_fake_wait_that_stops(stop)):
        await agent_monitor.scan_agents_loop(stop)

    # 停止后只跑了一轮 list_online
    assert svc.list_online.await_count == 1
