"""员工倡导积分榜自动化测试。"""
from __future__ import annotations

import random
import unittest
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import permutations

from advocacy import Fact, FactType, LeaderboardService
from advocacy.models import PAIR_CAP, STANDARD_POINTS

UTC = timezone.utc
ACT = "act-1"


def link(emp: int, ts: datetime, fid: str = "L") -> Fact:
    return Fact(fid, emp, ACT, ts, FactType.LINK)


def click(emp: int, ts: datetime, fid: str) -> Fact:
    return Fact(fid, emp, ACT, ts, FactType.CLICK)


def reference_awards(facts: list[Fact]) -> dict[str, int]:
    """独立参考实现：按发生时间升序、同刻按事实 ID 字典序从头计分。"""
    by_pair: dict[tuple[int, str], list[Fact]] = defaultdict(list)
    seen: set[str] = set()
    for fact in facts:
        if fact.fact_id in seen:
            continue
        seen.add(fact.fact_id)
        by_pair[(fact.employee_id, fact.activity_id)].append(fact)
    awards: dict[str, int] = {}
    for pair_facts in by_pair.values():
        remaining = PAIR_CAP
        for fact in sorted(pair_facts, key=lambda f: (f.occurred_at, f.fact_id)):
            awarded = min(STANDARD_POINTS[fact.fact_type], remaining)
            awards[fact.fact_id] = awarded
            remaining -= awarded
    return awards


def reference_board(
    facts: list[Fact], start: datetime | None, end: datetime | None
) -> list[tuple[int, int]]:
    """参考榜单：返回 [(employee_id, points)]，已按规则排序、剔除零分。"""
    awards = reference_awards(facts)
    seen: set[str] = set()
    points: dict[int, int] = defaultdict(int)
    for fact in facts:
        if fact.fact_id in seen:
            continue
        seen.add(fact.fact_id)
        awarded = awards[fact.fact_id]
        if awarded <= 0:
            continue
        if start is not None and fact.occurred_at < start:
            continue
        if end is not None and fact.occurred_at >= end:
            continue
        points[fact.employee_id] += awarded
    return sorted(
        ((emp, pts) for emp, pts in points.items() if pts > 0),
        key=lambda item: (-item[1], item[0]),
    )


def as_tuples(entries) -> list[tuple[int, int]]:
    return [(e.employee_id, e.points) for e in entries]


class LateClickScenarioTest(unittest.TestCase):
    """题目指定场景：补录迟到点击导致积分归属前移。"""

    def setUp(self) -> None:
        self.svc = LeaderboardService()
        self.jan = datetime(2026, 1, 1, tzinfo=UTC)
        self.feb = datetime(2026, 2, 1, tzinfo=UTC)
        self.week_feb2 = datetime(2026, 2, 2, tzinfo=UTC)  # 周一

        facts = [link(7, datetime(2026, 1, 26, tzinfo=UTC), "L1")]
        # 47 次点击分布在 1月26日至30日
        for i in range(47):
            ts = datetime(2026, 1, 26, tzinfo=UTC) + timedelta(hours=1 + i * 2)
            facts.append(click(7, ts, f"C{i:02d}"))
        # 2月2日 再一次点击
        facts.append(click(7, datetime(2026, 2, 2, tzinfo=UTC), "C47"))
        self.svc.submit(facts)

    def test_before_late_fact(self) -> None:
        self.assertEqual(as_tuples(self.svc.monthly_leaderboard(self.jan)), [(7, 99)])
        self.assertEqual(as_tuples(self.svc.monthly_leaderboard(self.feb)), [(7, 1)])
        self.assertEqual(as_tuples(self.svc.weekly_leaderboard(self.week_feb2)), [(7, 1)])
        self.assertEqual(as_tuples(self.svc.total_leaderboard()), [(7, 100)])

    def test_after_late_fact(self) -> None:
        late = click(7, datetime(2026, 1, 31, tzinfo=UTC), "LATE")
        self.assertEqual(self.svc.submit([late]), 1)
        self.assertEqual(as_tuples(self.svc.monthly_leaderboard(self.jan)), [(7, 100)])
        self.assertEqual(as_tuples(self.svc.monthly_leaderboard(self.feb)), [])
        self.assertEqual(as_tuples(self.svc.weekly_leaderboard(self.week_feb2)), [])
        self.assertEqual(as_tuples(self.svc.total_leaderboard()), [(7, 100)])

    def test_duplicate_late_fact_has_no_effect(self) -> None:
        late = click(7, datetime(2026, 1, 31, tzinfo=UTC), "LATE")
        self.svc.submit([late])
        before = (
            as_tuples(self.svc.monthly_leaderboard(self.jan)),
            as_tuples(self.svc.monthly_leaderboard(self.feb)),
            as_tuples(self.svc.weekly_leaderboard(self.week_feb2)),
            as_tuples(self.svc.total_leaderboard()),
        )
        self.assertEqual(self.svc.submit([late]), 0)  # 重复补录
        self.svc.submit([late, late])  # 批内重复
        after = (
            as_tuples(self.svc.monthly_leaderboard(self.jan)),
            as_tuples(self.svc.monthly_leaderboard(self.feb)),
            as_tuples(self.svc.weekly_leaderboard(self.week_feb2)),
            as_tuples(self.svc.total_leaderboard()),
        )
        self.assertEqual(before, after)


class OrderIndependenceTest(unittest.TestCase):
    """改变到达顺序与批次划分，结果与独立按时间排序重算一致。"""

    def make_facts(self, seed: int) -> list[Fact]:
        rng = random.Random(seed)
        facts: list[Fact] = []
        base = datetime(2026, 1, 26, tzinfo=UTC)
        counter = 0
        for emp in (1, 2, 3):
            for act in ("act-1", "act-2"):
                facts.append(Fact(f"L{emp}-{act}", emp, act, base, FactType.LINK))
                for _ in range(rng.randint(3, 60)):
                    counter += 1
                    # 跨周跨月：1月26日 起最多 40 天；允许相同时间戳
                    ts = base + timedelta(
                        days=rng.randint(0, 40), minutes=rng.choice([0, 0, 30])
                    )
                    facts.append(Fact(f"C{counter:04d}", emp, act, ts, FactType.CLICK))
        return facts

    def windows(self) -> list[tuple[str, datetime | None, datetime | None]]:
        return [
            ("total", None, None),
            ("jan", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)),
            ("feb", datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 3, 1, tzinfo=UTC)),
            ("w1", datetime(2026, 1, 26, tzinfo=UTC), datetime(2026, 2, 2, tzinfo=UTC)),
            ("w2", datetime(2026, 2, 2, tzinfo=UTC), datetime(2026, 2, 9, tzinfo=UTC)),
        ]

    def boards(self, svc: LeaderboardService) -> dict[str, list[tuple[int, int]]]:
        result: dict[str, list[tuple[int, int]]] = {}
        for name, start, end in self.windows():
            if name == "total":
                entries = svc.total_leaderboard()
            elif start.day == 1 and (end - start).days > 7:
                entries = svc.monthly_leaderboard(start)
            else:
                entries = svc.weekly_leaderboard(start)
            result[name] = as_tuples(entries)
        return result

    def check(self, facts: list[Fact], batches: list[list[Fact]]) -> None:
        svc = LeaderboardService()
        for batch in batches:
            svc.submit(batch)
        actual = self.boards(svc)
        for name, start, end in self.windows():
            expected = reference_board(facts, start, end)
            self.assertEqual(actual[name], expected, f"窗口 {name} 不一致")

    def test_single_batch_vs_many_batches(self) -> None:
        facts = self.make_facts(seed=42)
        self.check(facts, [facts])
        rng = random.Random(1)
        shuffled = facts[:]
        rng.shuffle(shuffled)
        # 保证每个对的建链先于其点击送达（上游约束）
        batches: list[list[Fact]] = []
        links = [f for f in shuffled if f.fact_type is FactType.LINK]
        clicks = [f for f in shuffled if f.fact_type is FactType.CLICK]
        batches.append(links)
        for i in range(0, len(clicks), 7):
            batches.append(clicks[i : i + 7])
        self.check(facts, batches)

    def test_duplicates_and_same_timestamps(self) -> None:
        facts = self.make_facts(seed=7)
        dup = facts[:]
        rng = random.Random(2)
        dup.extend(rng.sample(facts, 30))  # 重复提交，内容不变
        rng.shuffle(dup)
        links = [f for f in dup if f.fact_type is FactType.LINK]
        clicks = [f for f in dup if f.fact_type is FactType.CLICK]
        self.check(facts, [links] + [clicks[i : i + 13] for i in range(0, len(clicks), 13)])

    def test_late_facts_in_reverse_order(self) -> None:
        facts = self.make_facts(seed=99)
        links = [f for f in facts if f.fact_type is FactType.LINK]
        clicks = [f for f in facts if f.fact_type is FactType.CLICK]
        clicks.sort(key=lambda f: f.occurred_at, reverse=True)  # 完全倒序送达
        self.check(facts, [links] + [[c] for c in clicks])

    def test_all_permutations_of_small_case(self) -> None:
        base = datetime(2026, 1, 30, 23, tzinfo=UTC)
        facts = [
            link(5, base, "L"),
            click(5, base, "A"),                                  # 与建链同刻
            click(5, base, "B"),                                  # 同刻，按 ID 排序
            click(5, datetime(2026, 2, 1, tzinfo=UTC), "C"),      # 跨月
            click(5, datetime(2026, 2, 2, tzinfo=UTC), "D"),      # 跨周
        ]
        for perm in permutations(facts[1:]):
            self.check(facts, [[facts[0]], list(perm)])


class BoundaryTest(unittest.TestCase):
    """边界与排名规则。"""

    def test_zero_points_not_ranked_and_dense_ranks(self) -> None:
        svc = LeaderboardService()
        base = datetime(2026, 1, 5, tzinfo=UTC)  # 周一
        facts = [link(1, base, "L1"), link(2, base, "L2"), link(3, base, "L3")]
        # 员工1：1 次点击 -> 7 分；员工2：2 次点击 -> 9 分；员工3：仅建链 5 分
        facts.append(click(1, base + timedelta(hours=1), "a"))
        facts.append(click(2, base + timedelta(hours=1), "b"))
        facts.append(click(2, base + timedelta(hours=2), "c"))
        svc.submit(facts)
        board = svc.weekly_leaderboard(base)
        self.assertEqual(
            [(e.rank, e.employee_id, e.points) for e in board],
            [(1, 2, 9), (2, 1, 7), (3, 3, 5)],
        )

    def test_window_bounds_are_start_inclusive_end_exclusive(self) -> None:
        svc = LeaderboardService()
        w1 = datetime(2026, 1, 26, tzinfo=UTC)
        w2 = w1 + timedelta(days=7)
        svc.submit([
            link(1, w1, "L"),                       # 属于第一周（含起点）
            click(1, w2, "A"),                      # 属于第二周（不含终点）
            click(1, w1 + timedelta(microseconds=1), "B"),
        ])
        self.assertEqual(as_tuples(svc.weekly_leaderboard(w1)), [(1, 7)])
        self.assertEqual(as_tuples(svc.weekly_leaderboard(w2)), [(1, 2)])

    def test_invalid_window_start_rejected(self) -> None:
        svc = LeaderboardService()
        with self.assertRaises(ValueError):
            svc.weekly_leaderboard(datetime(2026, 1, 27, tzinfo=UTC))  # 周二
        with self.assertRaises(ValueError):
            svc.monthly_leaderboard(datetime(2026, 1, 2, tzinfo=UTC))  # 非 1 日

    def test_persistence_across_reopen(self) -> None:
        import os
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            base = datetime(2026, 1, 26, tzinfo=UTC)
            svc = LeaderboardService(db_path=path)
            svc.submit([link(1, base, "L"), click(1, base + timedelta(hours=1), "A")])
            svc.close()
            svc2 = LeaderboardService(db_path=path)
            self.assertEqual(as_tuples(svc2.total_leaderboard()), [(1, 7)])
            svc2.close()
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
