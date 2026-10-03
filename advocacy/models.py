"""数据类型定义：积分事实、榜单周期、榜单条目。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class FactType(Enum):
    """积分事实类型。"""

    LINK = "link"
    CLICK = "click"


STANDARD_POINTS: dict[FactType, int] = {
    FactType.LINK: 5,
    FactType.CLICK: 2,
}

PAIR_CAP = 100


@dataclass(frozen=True)
class Fact:
    """一条积分事实。occurred_at 为 UTC 发生时间（naive 时按 UTC 处理）。"""

    fact_id: str
    employee_id: int
    activity_id: str
    occurred_at: datetime
    fact_type: FactType


@dataclass(frozen=True)
class Period:
    """榜单周期：UTC 半开区间 [start, end)；两端均为 None 表示全部历史。"""

    start: datetime | None = None
    end: datetime | None = None

    @classmethod
    def all_time(cls) -> "Period":
        return cls(None, None)

    @classmethod
    def week_of(cls, moment: datetime) -> "Period":
        """包含 moment 的 UTC 自然周（周一零时起，含起点不含终点）。"""
        moment = _as_utc(moment)
        start = (moment - timedelta(days=moment.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return cls(start, start + timedelta(days=7))

    @classmethod
    def month(cls, year: int, month: int) -> "Period":
        """UTC 自然月（每月 1 日零时起，含起点不含终点）。"""
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        return cls(start, end)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


@dataclass(frozen=True)
class LeaderboardEntry:
    """榜单条目：连续名次、员工 ID、周期内得分。"""

    rank: int
    employee_id: int
    points: int
