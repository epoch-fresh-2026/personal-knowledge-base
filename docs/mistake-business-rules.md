# 错题学习模块 — 业务规则与统计口径

> 文档版本：1.0
> 更新日期：2026-11-16
> 适用范围：Issue #53 已确认规则
> 实现依据：`backend/modules/mistake/`（controller 与 service）
>
> 本文档记录错题学习中**已经实现**的统计口径与推荐算法参数，作为测试锁定依据。
> 所有权重、阈值与计算方式均与当前代码一致；后续修改算法须同步更新本文档与相关测试。

## 1. 错题与复习的数据归属

- `Mistake`（错题）与 `MistakeReviewRecord`（复习记录）的唯一正式模型定义在
  `modules/mistake/domain/models.py`；`modules/ingest/domain/models.py` 仅做向后兼容重导出，
  两者导入得到同一个 ORM 类对象。
- 错题与复习记录均带 `user_id`，归属于用户。所有错题接口使用
  `Depends(get_current_user)` 注入当前用户，查询与写入均按 `user_id` 隔离，
  用户只能查看、修改、复习、删除自己的错题。
- 错题采用物理删除，**不设软删除字段**（无 `is_deleted` / `deleted_at`）。
- 删除错题时使用 ORM `db.delete(mistake)`，依赖 relationship
  `cascade="all, delete-orphan"` 在同事务中一并删除其全部复习记录；
  不使用 bulk delete（bulk delete 不会触发 ORM 级联）。

## 2. 状态修改与完成复习是两个不同操作

- `PATCH /mistakes/{id}/status`：仅更新 `status`，**不增加** `review_count`、
  **不创建**复习记录、"不冒充"一次完整复习。
- `POST /mistakes/{id}/review`：在一次数据库事务中同时
  1) 更新 `Mistake.status`；
  2) `review_count += 1`；
  3) 更新 `last_reviewed_at`；
  4) 新增一条 `MistakeReviewRecord`。
  任一写入失败，整个事务回滚，不留部分更新。
- 合法状态值：`pending`、`reviewing`、`mastered`。

## 3. 学习概览的统计口径

接口：`GET /mistakes/analytics/overview`

| 字段 | 口径 |
|---|---|
| `total_mistakes`（错题总数） | 当前用户数据库中**实际存在**的错题记录数（物理未删除），不做软删除过滤 |
| `status_distribution`（状态分布） | 当前用户错题按 `status` 当前值计数（pending / reviewing / mastered） |
| `total_reviews`（累计复习次数） | 当前用户所有错题的 `review_count` **累加值** |
| `recorded_review_count`（复习历史记录数） | `mistake_review_records` 表中当前用户的记录条数 |
| `mastered_mistakes` | 当前用户状态为 `mastered` 的错题数 |
| `total_knowledge_points` / `weak_knowledge_points` | 见第 5 节知识点统计 |

**`total_reviews` 与 `recorded_review_count` 的区别**：
前者来自错题表累计字段之和，后者是独立复习记录表的实际条数。历史数据不一致或经过
状态直接修改时两者可能不同，因此接口分别返回、前端分别展示，不得相互替代或合并。

## 4. 学习趋势的统计口径

接口：`GET /mistakes/analytics/trends`（参数 `days` 7～365，`granularity` = day / week）

- **时间口径固定为 UTC**：统计窗口以 UTC 日期计算，`end_date` 取 UTC 当天，
  `start_date = end_date - (days - 1)`；窗口为左闭右开 `[start_datetime, end_datetime)`。
- 分桶：
  - 日粒度：按 UTC 日期分桶；
  - 周粒度：按该日期所在周的周一（ISO weekday）分桶。
- `review_count`：落在桶内、按复习记录 `reviewed_at` 归属日期统计的**复习记录条数**。
- `mastered_review_count`：其中 `status == "mastered"` 的复习记录条数。
- `new_mistake_count`：按错题 `created_at` 归属日期统计的新增错题数。
- 趋势**依据真实复习记录时间**计算，不通过错题当前状态推算历史复习。

## 5. 知识点统计口径

接口：`GET /mistakes/knowledge-points`

- 知识点来自错题的文本字段 `knowledge_points`，按既有分隔符
  `, ， 、 ; ； 换行` 拆分，去空白、去重（按 `casefold` 判重），
  **不创建独立知识点实体或数据表**。
- 仅统计当前用户自己的错题。
- 每个知识点：
  - `total_mistakes`：关联该知识点的错题数；
  - `unmastered_count = pending_count + reviewing_count`：未掌握错题数；
  - `weak_rate = unmastered_count / total_mistakes`（四舍五入 4 位）：薄弱率；
  - `status`：`weak`（存在未掌握）或 `mastered`（全部已掌握）。

## 6. 复习推荐算法（锁定当前实现，不得擅自变更权重）

接口：`GET /mistakes/recommendations`（`limit` 钳制到 `[1, 50]`）

### 6.1 候选范围
仅当前用户状态为 `pending` 或 `reviewing` 的错题进入候选；`mastered` 不进入推荐。

### 6.2 优先级分数（正向累加）

| 因子 | 条件 | 加分 |
|---|---|---|
| 状态基础分 | `status == pending` | +60 |
| 状态基础分 | `status == reviewing` | +35 |
| 薄弱知识点 | 关联任一 `status == weak` 的知识点 | `+ round(max(weak_rate) * 20)` |
| 距上次复习 | `last_reviewed_at is None` 且 `status == reviewing` | +10 |
| 距上次复习 | `days >= 7` | +20 |
| 距上次复习 | `3 <= days < 7` | +10 |

- `days = calculate_days_since_review(last_reviewed_at)`：按 UTC 计算距最近复习天数，
  兼容带/不带时区的时间，结果不小于 0；从未复习返回 `None`。

### 6.3 推荐等级阈值
- `score >= 60` → `high`
- `35 <= score < 60` → `medium`
- `score < 35` → `low`

### 6.4 排序规则
1. `priority_score` 降序；
2. `days_since_last_review` 降序（`None` 视为 0）；
3. `mistake_id` 升序（稳定兜底）。

最终返回前 `limit` 条，并给出匹配薄弱知识点（最多 3 条）和距复习天数等推荐理由。
