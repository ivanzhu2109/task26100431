# 员工倡导积分榜

纯 Python 库，由上层直接调用；积分事实与计算结果持久化在 SQLite（默认内存库，可传文件路径）。

## 规则

- 每个员工活动对只有一个建链事实，计 5 分；每个唯一点击计 2 分。
- 员工活动对总上限 100 分，作用于全部历史，不重置。
- 同一对的事实按发生时间升序、同一时刻按事实 ID 字典序依次入账；
  每条实际得分取标准分与剩余额度的较小值，额度耗尽后计 0 分。
- 迟到事实参与上述排序，会挤掉原先较晚事实的积分；积分归属于事实的发生时间。
- 同一事实（相同事实 ID）重复提交不产生额外积分。
- 榜单按得分降序、员工整数 ID 升序排连续名次，零分不入榜；
  周/月窗口含起点、不含终点。

## 使用

```python
from datetime import datetime, timezone
from advocacy import Fact, FactType, LeaderboardService

svc = LeaderboardService(db_path="leaderboard.sqlite3")  # 缺省 ":memory:"

svc.submit([
    Fact("fact-1", 7, "act-1", datetime(2026, 1, 26, tzinfo=timezone.utc), FactType.LINK),
    Fact("fact-2", 7, "act-1", datetime(2026, 1, 27, tzinfo=timezone.utc), FactType.CLICK),
])

svc.total_leaderboard()                                  # 全部历史
svc.weekly_leaderboard(datetime(2026, 1, 26, tzinfo=timezone.utc))   # 自然周，须为周一零时
svc.monthly_leaderboard(datetime(2026, 1, 1, tzinfo=timezone.utc))   # 自然月，须为 1 日零时
```

- `submit(facts)` 批量接收事实，返回新入库条数；重复事实被忽略。
- 榜单方法返回 `LeaderboardEntry(rank, employee_id, points)` 列表。
- 时间参数建议带 UTC 时区；naive 时间按 UTC 处理。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

覆盖：迟到补录挤占积分（1 月 99→100、2 月 1→0、总分不变）、重复提交无效、
到达顺序与批次划分无关性（与独立按时间排序重算的参考实现对比）、
相同时间戳按事实 ID 排序、跨周跨月窗口边界、连续名次与零分不入榜、SQLite 持久化重开。
