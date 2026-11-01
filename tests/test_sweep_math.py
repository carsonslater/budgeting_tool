"""
tests/test_sweep_math.py

Pure month-end arithmetic: fund settlement, leftover, and the goal split.
No database.
"""

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sweep_math import allocate, fund_month, leftover


def rule(goal_id, rank, kind, amount):
    return {
        "goal_id": goal_id,
        "priority_rank": rank,
        "allocation_type": kind,
        "amount": amount,
    }


class TestFundMonth:
    def test_reserve_covers_a_bill_in_the_same_month(self):
        step = fund_month(balance_before=0.0, reserve=100.0, spent=80.0)
        assert (step.draw, step.shortfall, step.balance_after) == (80.0, 0.0, 20.0)

    def test_an_uncovered_bill_is_a_shortfall_and_the_fund_never_goes_negative(self):
        step = fund_month(balance_before=200.0, reserve=100.0, spent=1200.0)
        assert (step.draw, step.shortfall, step.balance_after) == (300.0, 900.0, 0.0)

    def test_no_spend_only_accumulates(self):
        step = fund_month(balance_before=50.0, reserve=100.0, spent=0.0)
        assert (step.draw, step.shortfall, step.balance_after) == (0.0, 0.0, 150.0)

    def test_negative_inputs_are_rejected(self):
        with pytest.raises(ValueError):
            fund_month(0.0, -1.0, 0.0)
        with pytest.raises(ValueError):
            fund_month(0.0, 0.0, -1.0)


class TestLeftover:
    def test_subtracts_regular_spend_reserves_and_shortfall(self):
        assert leftover(3000.0, 350.0, 100.0, 0.0) == 2550.0
        assert leftover(3000.0, 350.0, 100.0, 900.0) == 1650.0

    def test_may_be_negative(self):
        assert leftover(1000.0, 1200.0, 0.0, 0.0) == -200.0


class TestAllocate:
    def test_fixed_then_percentage_of_the_remainder(self):
        rules = [rule(1, 1, "fixed", 300.0), rule(2, 2, "percentage", 50.0)]
        grants, unallocated = allocate(2550.0, rules, {1: 1000.0, 2: 2000.0})
        assert grants == {1: 300.0, 2: 1125.0}
        assert unallocated == 1125.0

    def test_fixed_amounts_are_capped_by_the_pot(self):
        rules = [rule(1, 1, "fixed", 500.0), rule(2, 2, "fixed", 500.0)]
        grants, unallocated = allocate(600.0, rules, {1: 9999.0, 2: 9999.0})
        assert grants == {1: 500.0, 2: 100.0}
        assert unallocated == 0.0

    def test_grants_are_capped_by_each_goals_need(self):
        rules = [rule(1, 1, "fixed", 300.0), rule(2, 2, "percentage", 100.0)]
        grants, unallocated = allocate(1000.0, rules, {1: 100.0, 2: 200.0})
        assert grants == {1: 100.0, 2: 200.0}
        assert unallocated == 700.0

    def test_a_capped_goal_does_not_overflow_to_the_next(self):
        rules = [rule(1, 1, "percentage", 100.0), rule(2, 2, "percentage", 50.0)]
        grants, unallocated = allocate(1000.0, rules, {1: 100.0, 2: 5000.0})
        assert grants[1] == 100.0
        assert grants[2] == 500.0
        assert unallocated == 400.0

    def test_goals_outside_needs_are_ignored(self):
        rules = [rule(1, 1, "fixed", 300.0), rule(2, 2, "fixed", 300.0)]
        grants, unallocated = allocate(1000.0, rules, {1: 500.0})
        assert grants == {1: 300.0}
        assert unallocated == 700.0

    def test_a_negative_pot_allocates_nothing(self):
        grants, unallocated = allocate(-50.0, [rule(1, 1, "fixed", 10.0)], {1: 100.0})
        assert grants == {}
        assert unallocated == 0.0

    def test_priority_order_is_respected_regardless_of_input_order(self):
        rules = [rule(2, 2, "fixed", 400.0), rule(1, 1, "fixed", 400.0)]
        grants, _ = allocate(500.0, rules, {1: 1000.0, 2: 1000.0})
        assert grants == {1: 400.0, 2: 100.0}

    def test_conservation_holds_for_random_inputs(self):
        rng = random.Random(7319)
        for _ in range(300):
            pot = round(rng.uniform(0, 5000), 2)
            goal_ids = list(range(1, rng.randint(1, 5) + 1))
            needs = {g: round(rng.uniform(0, 3000), 2) for g in goal_ids}
            rules = []
            pct_left = 100.0
            for rank, g in enumerate(goal_ids):
                if rng.random() < 0.5:
                    rules.append(rule(g, rank, "fixed", round(rng.uniform(0, 1000), 2)))
                else:
                    share = round(rng.uniform(0, pct_left), 2)
                    pct_left -= share
                    rules.append(rule(g, rank, "percentage", share))
            grants, unallocated = allocate(pot, rules, needs)
            assert all(v > 0 for v in grants.values())
            assert all(grants[g] <= needs[g] + 1e-9 for g in grants)
            assert abs(sum(grants.values()) + unallocated - pot) < 0.005
            assert unallocated >= -1e-9
