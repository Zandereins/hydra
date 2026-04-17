"""Budget tracker. Single Lock-guarded accumulator. Propagates via TaskGroup cancel."""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenUsage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0


class BudgetExceeded(Exception):
    """Hard cap tripped."""

    def __init__(self, spent: float, max_: float) -> None:
        self.spent = spent
        self.max = max_
        super().__init__(f"budget exceeded: ${spent:.4f} > ${max_:.4f}")


class Budget:
    """Thread/coroutine-safe USD accumulator with hard + soft caps."""

    def __init__(self, hard_cap_usd: float, soft_cap_usd: float) -> None:
        self.hard_cap_usd = hard_cap_usd
        self.soft_cap_usd = soft_cap_usd
        self.spent_usd = 0.0
        self.soft_cap_hit = False
        self._lock = threading.Lock()

    def charge(
        self,
        usage: TokenUsage,
        *,
        price_in: float,
        price_out: float,
        price_cache_read: float | None = None,
        price_cache_write_5m: float | None = None,
        price_cache_write_1h: float | None = None,
    ) -> None:
        cost = usage.input * price_in + usage.output * price_out
        if price_cache_read is not None:
            cost += usage.cache_read * price_cache_read
        if price_cache_write_5m is not None:
            cost += usage.cache_write_5m * price_cache_write_5m
        if price_cache_write_1h is not None:
            cost += usage.cache_write_1h * price_cache_write_1h

        with self._lock:
            projected = self.spent_usd + cost
            if projected >= self.hard_cap_usd:
                raise BudgetExceeded(projected, self.hard_cap_usd)
            if projected >= self.soft_cap_usd and not self.soft_cap_hit:
                self.soft_cap_hit = True
            self.spent_usd = projected
