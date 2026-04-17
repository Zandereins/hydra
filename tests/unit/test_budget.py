import asyncio

import pytest

from hydra.budget import Budget, BudgetExceeded, TokenUsage


def test_charge_below_cap_succeeds() -> None:
    b = Budget(hard_cap_usd=2.00, soft_cap_usd=1.10)
    b.charge(TokenUsage(input=1000, output=500), price_in=3e-6, price_out=15e-6)
    assert b.spent_usd == 1000 * 3e-6 + 500 * 15e-6


def test_charge_exceeds_hard_cap_raises() -> None:
    b = Budget(hard_cap_usd=0.01, soft_cap_usd=0.005)
    with pytest.raises(BudgetExceeded) as exc:
        b.charge(TokenUsage(input=100_000, output=1_000), price_in=3e-6, price_out=15e-6)
    assert exc.value.spent > 0.01


def test_soft_cap_warning_emitted() -> None:
    b = Budget(hard_cap_usd=2.00, soft_cap_usd=0.01)
    b.charge(TokenUsage(input=10_000, output=0), price_in=3e-6, price_out=15e-6)
    assert b.soft_cap_hit is True
    assert b.spent_usd < 2.00  # didn't trip hard cap


@pytest.mark.asyncio
async def test_concurrent_charges_respect_lock() -> None:
    b = Budget(hard_cap_usd=0.10, soft_cap_usd=0.05)

    async def charge_small() -> None:
        b.charge(TokenUsage(input=1000, output=100), price_in=3e-6, price_out=15e-6)

    await asyncio.gather(*[charge_small() for _ in range(5)])
    # Each call: 1000*3e-6 + 100*15e-6 = 0.0045; 5 calls = 0.0225
    assert 0.022 < b.spent_usd < 0.023


def test_budget_exceeded_carries_context() -> None:
    b = Budget(hard_cap_usd=0.001, soft_cap_usd=0.0005)
    try:
        b.charge(TokenUsage(input=1_000_000, output=0), price_in=3e-6, price_out=15e-6)
    except BudgetExceeded as exc:
        assert exc.max == 0.001
        assert exc.spent > 0.001
