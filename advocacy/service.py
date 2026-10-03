"""对外服务：批量接收事实、重算积分、查询榜单。"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .models import PAIR_CAP, STANDARD_POINTS, Fact, LeaderboardEntry
from .store import FactStore


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _compute_awards(facts: list[Fact]) -> dict[str, int]:
    """按发生时间升序、同刻按事实 ID 字典序，对一个员工活动对从头计分。"""
    ordered = sorted(facts, key=lambda f: (f.occurred_at, f.fact_id))
    remaining = PAIR_CAP
    awards: dict[str, int] = {}
    for fact in ordered:
        awarded = min(STANDARD_POINTS[fact.fact_type], remaining)
        awards[fact.fact_id] = awarded
        remaining -= awarded
    return awards


def _to_entries(points_by_employee: dict[int, int]) -> list[LeaderboardEntry]:
    """按得分降序、员工 ID 升序排出连续名次，零分不入榜。"""
    rows = sorted(
        ((emp, pts) for emp, pts in points_by_employee.items() if pts > 0),
        key=lambda item: (-item[1], item[0]),
    )
    return [
        LeaderboardEntry(rank=index + 1, employee_id=emp, points=pts)
        for index, (emp, pts) in enumerate(rows)
    ]


class LeaderboardService:
    """员工倡导积分榜。"""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._store = FactStore(db_path)

    def submit(self, facts: list[Fact]) -> int:
        """批量接收积分事实，返回新入库的事实条数。

        重复提交（相同事实 ID）被忽略；受影响员工活动对的积分按
        发生时间顺序从头重算，迟到事实会挤掉原先较晚事实的积分。
        """
        inserted = self._store.add_facts(facts)
        pairs = {(f.employee_id, f.activity_id) for f in inserted}
        for pair in sorted(pairs):
            pair_facts = self._store.facts_for_pairs({pair})
            awards = _compute_awards(pair_facts)
            self._store.save_awards(awards)
        return len(inserted)

    def _leaderboard_between(
        self, start: datetime | None, end: datetime | None
    ) -> list[LeaderboardEntry]:
        points_by_employee: dict[int, int] = defaultdict(int)
        for fact, awarded in self._store.awarded_facts():
            if awarded <= 0:
                continue
            occurred = _as_utc(fact.occurred_at)
            if start is not None and occurred < start:
                continue
            if end is not None and occurred >= end:
                continue
            points_by_employee[fact.employee_id] += awarded
        return _to_entries(points_by_employee)

    def total_leaderboard(self) -> list[LeaderboardEntry]:
        """全部历史总榜。"""
        return self._leaderboard_between(None, None)

    def weekly_leaderboard(self, week_start: datetime) -> list[LeaderboardEntry]:
        """指定 UTC 自然周（周一零时起，含起点不含终点）的榜单。"""
        start = _as_utc(week_start)
        if start.weekday() != 0 or (start.hour, start.minute, start.second, start.microsecond) != (0, 0, 0, 0):
            raise ValueError("week_start 必须是 UTC 周一零时")
        return self._leaderboard_between(start, start + timedelta(days=7))

    def monthly_leaderboard(self, month_start: datetime) -> list[LeaderboardEntry]:
        """指定 UTC 自然月（1 日零时起，含起点不含终点）的榜单。"""
        start = _as_utc(month_start)
        if start.day != 1 or (start.hour, start.minute, start.second, start.microsecond) != (0, 0, 0, 0):
            raise ValueError("month_start 必须是 UTC 每月 1 日零时")
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return self._leaderboard_between(start, end)

    def close(self) -> None:
        self._store.close()
