"""SQLite 持久化：事实表与积分结果表，以及对受影响员工活动对的重算。"""

from __future__ import annotations

import sqlite3
from datetime import timezone

from .models import PAIR_CAP, STANDARD_POINTS, Fact, FactType

_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


def format_time(moment) -> str:
    """格式化为定长 UTC 字符串，使字典序与时间序一致。"""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime(_TIME_FORMAT)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    activity_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    fact_type TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_pair
    ON facts (employee_id, activity_id, occurred_at, fact_id);

CREATE TABLE IF NOT EXISTS awards (
    fact_id TEXT PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    activity_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    points INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_awards_time
    ON awards (occurred_at);
"""


class Store:
    """封装 SQLite 连接，负责事实落库（幂等）与按对重算积分。"""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def commit(self) -> None:
        self._conn.commit()

    def insert_facts(self, facts: list[Fact]) -> set[tuple[int, str]]:
        """幂等写入事实，返回实际发生变化的 (employee_id, activity_id) 对集合。"""
        changed: set[tuple[int, str]] = set()
        for fact in facts:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO facts"
                " (fact_id, employee_id, activity_id, occurred_at, fact_type)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    fact.fact_id,
                    fact.employee_id,
                    fact.activity_id,
                    format_time(fact.occurred_at),
                    fact.fact_type.value,
                ),
            )
            if cursor.rowcount:
                changed.add((fact.employee_id, fact.activity_id))
        return changed

    def recompute_pairs(self, pairs: set[tuple[int, str]]) -> None:
        """按发生时间升序、事实 ID 字典序对给定对从头重算积分。"""
        for employee_id, activity_id in pairs:
            rows = self._conn.execute(
                "SELECT fact_id, occurred_at, fact_type FROM facts"
                " WHERE employee_id = ? AND activity_id = ?"
                " ORDER BY occurred_at, fact_id",
                (employee_id, activity_id),
            ).fetchall()
            self._conn.execute(
                "DELETE FROM awards WHERE employee_id = ? AND activity_id = ?",
                (employee_id, activity_id),
            )
            remaining = PAIR_CAP
            for fact_id, occurred_at, fact_type in rows:
                standard = STANDARD_POINTS[FactType(fact_type)]
                points = min(standard, remaining)
                remaining -= points
                if points > 0:
                    self._conn.execute(
                        "INSERT INTO awards"
                        " (fact_id, employee_id, activity_id, occurred_at, points)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (fact_id, employee_id, activity_id, occurred_at, points),
                    )

    def points_by_employee(
        self, start: str | None, end: str | None
    ) -> list[tuple[int, int]]:
        """返回区间内各员工得分（正分），按得分降序、员工 ID 升序。"""
        query = "SELECT employee_id, SUM(points) FROM awards"
        conditions: list[str] = []
        params: list[str] = []
        if start is not None:
            conditions.append("occurred_at >= ?")
            params.append(start)
        if end is not None:
            conditions.append("occurred_at < ?")
            params.append(end)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " GROUP BY employee_id ORDER BY SUM(points) DESC, employee_id ASC"
        return [
            (employee_id, points)
            for employee_id, points in self._conn.execute(query, params).fetchall()
        ]
