"""积分榜库的自动化测试。"""

import random
import sys
import unittest
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advocacy import AdvocacyService, Fact, FactType, Period

UTC = timezone.utc


def make_fact(fact_id, employee_id, activity_id, occurred_at, fact_type):
    return Fact(
        fact_id=fact_id,
        employee_id=employee_id,
        activity_id=activity_id,
        occurred_at=occurred_at,
        fact_type=fact_type,
    )


def reference_awards(facts):
    """独立参考实现：按发生时间排序后从头计算每条事实的实际得分。"""
    unique = {fact.fact_id: fact for fact in facts}
    groups = defaultdict(list)
    for fact in unique.values():
        groups[(fact.employee_id, fact.activity_id)].append(fact)
    awards = []
    for pair_facts in groups.values():
        pair_facts.sort(key=lambda f: (f.occurred_at, f.fact_id))
        remaining = 100
        for fact in pair_facts:
            standard = 5 if fact.fact_type is FactType.LINK else 2
            points = min(standard, remaining)
            remaining -= points
            if points > 0:
                awards.append((fact.employee_id, fact.occurred_at, points))
    return awards


def reference_board(awards, start=None, end=None):
    totals = defaultdict(int)
    for employee_id, occurred_at, points in awards:
        if start is not None and occurred_at < start:
            continue
        if end is not None and occurred_at >= end:
            continue
        totals[employee_id] += points
    return sorted(
        ((emp, pts) for emp, pts in totals.items() if pts > 0),
        key=lambda item: (-item[1], item[0]),
    )


def service_board(service, period):
    return [(entry.employee_id, entry.points) for entry in service.leaderboard(period)]


class BackfillScenarioTest(unittest.TestCase):
    """题目指定的迟到补录场景。"""

    def setUp(self):
        self.service = AdvocacyService(":memory:")
        self.employee = 42
        self.activity = "act-1"
        base = datetime(2026, 1, 26, 9, 0, tzinfo=UTC)
        facts = [
            make_fact("link", self.employee, self.activity, base, FactType.LINK)
        ]
        for index in range(47):
            occurred = base + timedelta(hours=1 + index * 2)
            assert occurred < datetime(2026, 1, 31, tzinfo=UTC)
            facts.append(
                make_fact(
                    f"click-{index:02d}",
                    self.employee,
                    self.activity,
                    occurred,
                    FactType.CLICK,
                )
            )
        facts.append(
            make_fact(
                "click-feb2",
                self.employee,
                self.activity,
                datetime(2026, 2, 2, 8, 0, tzinfo=UTC),
                FactType.CLICK,
            )
        )
        self.service.submit_facts(facts)

    def tearDown(self):
        self.service.close()

    def board_points(self, period):
        return dict(service_board(self.service, period))

    def test_before_backfill(self):
        self.assertEqual(
            self.board_points(Period.month(2026, 1)), {self.employee: 99}
        )
        self.assertEqual(self.board_points(Period.month(2026, 2)), {self.employee: 1})
        week = Period.week_of(datetime(2026, 2, 2, 12, tzinfo=UTC))
        self.assertEqual(self.board_points(week), {self.employee: 1})
        self.assertEqual(self.board_points(Period.all_time()), {self.employee: 100})

    def test_after_backfill(self):
        late = make_fact(
            "click-jan31",
            self.employee,
            self.activity,
            datetime(2026, 1, 31, 23, 0, tzinfo=UTC),
            FactType.CLICK,
        )
        self.service.submit_facts([late])

        self.assertEqual(
            self.board_points(Period.month(2026, 1)), {self.employee: 100}
        )
        self.assertEqual(self.board_points(Period.month(2026, 2)), {})
        week = Period.week_of(datetime(2026, 2, 2, 12, tzinfo=UTC))
        self.assertEqual(self.board_points(week), {})
        self.assertEqual(self.board_points(Period.all_time()), {self.employee: 100})

        self.service.submit_facts([late])
        self.assertEqual(
            self.board_points(Period.month(2026, 1)), {self.employee: 100}
        )
        self.assertEqual(self.board_points(Period.all_time()), {self.employee: 100})


class ArrivalOrderInvariantTest(unittest.TestCase):
    """重复提交、时间相同、跨周跨月、任意到达顺序与批次划分的一致性。"""

    def build_facts(self):
        rng = random.Random(20261004)
        facts = []
        start = datetime(2026, 1, 20, tzinfo=UTC)
        end = datetime(2026, 2, 12, tzinfo=UTC)
        span_seconds = int((end - start).total_seconds())
        counter = 0
        for employee_id in (11, 22, 33, 44, 55):
            for activity in ("act-a", "act-b", "act-c"):
                link_time = start + timedelta(
                    seconds=rng.randrange(span_seconds // 3)
                )
                facts.append(
                    make_fact(
                        f"f{counter:04d}",
                        employee_id,
                        activity,
                        link_time,
                        FactType.LINK,
                    )
                )
                counter += 1
                for _ in range(rng.randrange(40, 65)):
                    offset = rng.randrange(span_seconds)
                    if rng.random() < 0.2:
                        offset -= offset % 3600
                    occurred = link_time + timedelta(seconds=1 + offset)
                    facts.append(
                        make_fact(
                            f"f{counter:04d}",
                            employee_id,
                            activity,
                            occurred,
                            FactType.CLICK,
                        )
                    )
                    counter += 1
        return facts

    def all_periods(self):
        periods = [Period.all_time()]
        day = datetime(2026, 1, 19, tzinfo=UTC)
        while day < datetime(2026, 2, 16, tzinfo=UTC):
            periods.append(Period.week_of(day))
            day += timedelta(days=7)
        periods.append(Period.month(2026, 1))
        periods.append(Period.month(2026, 2))
        return periods

    def test_shuffled_arrival_matches_reference(self):
        facts = self.build_facts()
        reference = reference_awards(facts)

        rng = random.Random(99)
        shuffled = facts[:]
        rng.shuffle(shuffled)
        submissions = []
        for fact in shuffled:
            submissions.append(fact)
            if rng.random() < 0.15:
                submissions.append(fact)
        rng.shuffle(submissions)

        service = AdvocacyService(":memory:")
        try:
            cursor = 0
            while cursor < len(submissions):
                size = rng.randrange(1, 40)
                service.submit_facts(submissions[cursor : cursor + size])
                cursor += size
            service.submit_facts(rng.sample(facts, 50))

            for period in self.all_periods():
                expected = reference_board(reference, period.start, period.end)
                actual = service_board(service, period)
                self.assertEqual(actual, expected, f"period {period}")
        finally:
            service.close()

    def test_ranks_are_consecutive(self):
        service = AdvocacyService(":memory:")
        try:
            moment = datetime(2026, 3, 2, 10, tzinfo=UTC)
            facts = []
            for employee_id in (5, 3, 9):
                facts.append(
                    make_fact(
                        f"link-{employee_id}",
                        employee_id,
                        f"act-{employee_id}",
                        moment,
                        FactType.LINK,
                    )
                )
            service.submit_facts(facts)
            board = service.leaderboard(Period.all_time())
            self.assertEqual([entry.rank for entry in board], [1, 2, 3])
            self.assertEqual([entry.employee_id for entry in board], [3, 5, 9])
        finally:
            service.close()


class PersistenceTest(unittest.TestCase):
    """SQLite 文件持久化：重开后榜单不变。"""

    def test_reopen_keeps_results(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "board.db")
            fact = make_fact(
                "link-1",
                7,
                "act-1",
                datetime(2026, 1, 26, 10, tzinfo=UTC),
                FactType.LINK,
            )
            with AdvocacyService(db_path) as service:
                service.submit_facts([fact])
            with AdvocacyService(db_path) as service:
                self.assertEqual(
                    service_board(service, Period.all_time()), [(7, 5)]
                )
                service.submit_facts([fact])
                self.assertEqual(
                    service_board(service, Period.all_time()), [(7, 5)]
                )


if __name__ == "__main__":
    unittest.main()
