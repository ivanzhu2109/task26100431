# 员工倡导积分榜库

纯 Python + SQLite 实现，无外部依赖、无网络服务，由上层直接实例化调用。
积分事实与计算结果均持久化在 SQLite 中。

## 规则

- 每个员工活动对（employee_id, activity_id）只有一个建链事实，计 5 分；每个唯一点击计 2 分。
- 每个员工活动对历史总上限 100 分，不按周/月重置。
- 同一对的事实按发生时间升序、同时刻按事实 ID 字典序依次入账；
  每条实际得分 = min(标准分, 剩余额度)，额度耗尽后计 0 分。
- 迟到补录的事实参与上述排序，可能挤掉较晚事实的积分；
  积分归属于实际获分事实的发生时间（UTC），与提交时间无关。
- 同一事实（稳定事实 ID）重复提交不产生额外积分；批内顺序不影响结果。

## 使用

```python
from datetime import datetime, timezone
from advocacy import AdvocacyService, Fact, FactType, Period

svc = AdvocacyService("board.db")          # 或 ":memory:"

svc.submit_facts([
    Fact("f-001", 42, "act-1",
         datetime(2026, 1, 26, 9, 0, tzinfo=timezone.utc), FactType.LINK),
    Fact("f-002", 42, "act-1",
         datetime(2026, 1, 26, 10, 0, tzinfo=timezone.utc), FactType.CLICK),
])

svc.leaderboard(Period.all_time())                       # 总榜
svc.leaderboard(Period.week_of(datetime(2026, 1, 28)))   # 该时刻所在自然周（周一起）
svc.leaderboard(Period.month(2026, 1))                   # 2026 年 1 月自然月
# 返回 [LeaderboardEntry(rank=1, employee_id=42, points=7), ...]
# 按得分降序、员工 ID 升序排出连续名次，零分不入榜

svc.close()                                # 也支持 with 语句
```

说明：

- `occurred_at` 为 UTC 时间；naive datetime 按 UTC 处理。
- 每批 `submit_facts` 在单个事务内完成落库与受影响对的重算，
  提交完成后周榜、月榜、总榜立即反映同一批事实。

## 实现结构

- `advocacy/models.py` — `Fact` / `FactType` / `Period` / `LeaderboardEntry` 类型定义。
- `advocacy/store.py` — SQLite 表结构（`facts`、`awards`）、幂等写入、按对重算。
- `advocacy/service.py` — 对外接口 `AdvocacyService`（批量提交、榜单查询）。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

覆盖：题目指定的迟到补录场景（1 月 99→100、2 月 1→0、周榜失分、总分不变、
重复补录无影响），以及重复提交、时间相同、跨周跨月数据在随机到达顺序与
批次划分下与独立参考实现的全部榜单一致性、连续名次、SQLite 持久化重开。
