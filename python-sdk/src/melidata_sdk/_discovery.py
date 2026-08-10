from __future__ import annotations

import random
import time

from .models import Agent


class AgentPool:
    def __init__(self, *, region: str | None, cache_ttl: float) -> None:
        self.region = region
        self.cache_ttl = cache_ttl
        self._agents: list[Agent] = []
        self._updated_at = 0.0
        self._random: random.Random = random.SystemRandom()

    @property
    def is_fresh(self) -> bool:
        return (
            bool(self._agents)
            and self.cache_ttl > 0
            and (time.monotonic() - self._updated_at < self.cache_ttl)
        )

    def update(self, agents: list[Agent]) -> list[Agent]:
        filtered = [
            agent
            for agent in agents
            if agent.status == "ready"
            and (self.region is None or agent.region == self.region)
        ]
        unique: dict[str, Agent] = {}
        for agent in filtered:
            unique.setdefault(agent.base_url, agent)
        self._agents = list(unique.values())
        self._updated_at = time.monotonic()
        return list(self._agents)

    def invalidate(self) -> None:
        self._updated_at = 0.0

    def candidates(self) -> list[Agent]:
        remaining = list(self._agents)
        ordered: list[Agent] = []
        while remaining:
            total = sum(max(1, agent.weight) for agent in remaining)
            selected = self._random.uniform(0, total)
            cursor = 0.0
            selected_index = len(remaining) - 1
            for index, agent in enumerate(remaining):
                cursor += max(1, agent.weight)
                if selected <= cursor:
                    selected_index = index
                    break
            ordered.append(remaining.pop(selected_index))
        return ordered
