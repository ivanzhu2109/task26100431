"""对外服务接口：批量接收事实、查询榜单。"""

from __future__ import annotations

from collections.abc import Iterable

from .models import Fact, LeaderboardEntry, Period
from .store import Store, format_time


class AdvocacyService:
    """员工倡导积分榜服务，由上层直接实例化调用。"""

    def __init__(self, db_path: str) -> None:
        self._store = Store(db_path)

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> "AdvocacyService":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def submit_facts(self, facts: Iterable[Fact]) -> None:
        """批量接收积分事实；重复事实被忽略；批内顺序不影响结果。"""
        changed = self._store.insert_facts(list(facts))
        self._store.recompute_pairs(changed)
        self._store.commit()

    def leaderboard(self, period: Period) -> list[LeaderboardEntry]:
        """查询指定周期榜单，零分不入榜，名次连续。"""
        start = format_time(period.start) if period.start is not None else None
        end = format_time(period.end) if period.end is not None else None
        rows = self._store.points_by_employee(start, end)
        return [
            LeaderboardEntry(rank=index + 1, employee_id=employee_id, points=points)
            for index, (employee_id, points) in enumerate(rows)
        ]
