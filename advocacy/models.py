"""数据模型：积分事实与榜单条目。"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class FactType(enum.Enum):
    """积分事实类型。"""

    LINK = "link"    # 建链，标准分 5
    CLICK = "click"  # 唯一点击，标准分 2


STANDARD_POINTS: dict[FactType, int] = {
    FactType.LINK: 5,
    FactType.CLICK: 2,
}

PAIR_CAP = 100  # 员工活动对的积分上限


@dataclass(frozen=True)
class Fact:
    """一条积分事实。

    fact_id: 稳定的事实 ID，重复提交内容不变。
    employee_id: 员工整数 ID。
    activity_id: 活动 ID。
    occurred_at: UTC 发生时间（要求 tzinfo 为 UTC 或 naive 视为 UTC）。
    fact_type: 建链或唯一点击。
    """

    fact_id: str
    employee_id: int
    activity_id: str
    occurred_at: datetime
    fact_type: FactType


@dataclass(frozen=True)
class LeaderboardEntry:
    """榜单条目：连续名次、员工与得分。"""

    rank: int
    employee_id: int
    points: int
