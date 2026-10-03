"""SQLite 持久化层：事实存储与按对读取。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .models import Fact, FactType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    activity_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    awarded INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_facts_pair ON facts (employee_id, activity_id);
"""


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_to_fact(row: tuple) -> Fact:
    return Fact(
        fact_id=row[0],
        employee_id=row[1],
        activity_id=row[2],
        occurred_at=_from_iso(row[3]),
        fact_type=FactType(row[4]),
    )


class FactStore:
    """积分事实的 SQLite 存储。"""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def add_facts(self, facts: list[Fact]) -> list[Fact]:
        """批量写入事实（幂等），返回本次新入库的事实。"""
        inserted: list[Fact] = []
        with self._conn:
            for fact in facts:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO facts"
                    " (fact_id, employee_id, activity_id, occurred_at, fact_type)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        fact.fact_id,
                        fact.employee_id,
                        fact.activity_id,
                        _to_iso(fact.occurred_at),
                        fact.fact_type.value,
                    ),
                )
                if cur.rowcount > 0:
                    inserted.append(fact)
        return inserted

    def facts_for_pairs(self, pairs: set[tuple[int, str]]) -> list[Fact]:
        """读取指定员工活动对的全部事实。"""
        result: list[Fact] = []
        for employee_id, activity_id in pairs:
            cur = self._conn.execute(
                "SELECT fact_id, employee_id, activity_id, occurred_at, fact_type"
                " FROM facts WHERE employee_id = ? AND activity_id = ?",
                (employee_id, activity_id),
            )
            result.extend(_row_to_fact(row) for row in cur.fetchall())
        return result

    def awarded_facts(self) -> list[tuple[Fact, int]]:
        """读取全部事实及其实际得分。"""
        cur = self._conn.execute(
            "SELECT fact_id, employee_id, activity_id, occurred_at, fact_type, awarded"
            " FROM facts"
        )
        return [(_row_to_fact(row[:5]), row[5]) for row in cur.fetchall()]

    def save_awards(self, awards: dict[str, int]) -> None:
        """保存事实的实际得分。"""
        with self._conn:
            self._conn.executemany(
                "UPDATE facts SET awarded = ? WHERE fact_id = ?",
                [(points, fact_id) for fact_id, points in awards.items()],
            )

    def close(self) -> None:
        self._conn.close()
