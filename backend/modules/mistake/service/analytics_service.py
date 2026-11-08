from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from modules.ingest.domain.models import Mistake, MistakeReviewRecord
from modules.mistake.service.knowledge_point_service import (
    get_knowledge_point_statistics,
)


def get_learning_overview(
    db: Session,
    user_id: str,
) -> dict:
    """获取指定用户的学习数据概览。"""

    mistakes = (
        db.query(Mistake)
        .filter(Mistake.user_id == user_id)
        .all()
    )

    status_distribution = {
        "pending": 0,
        "reviewing": 0,
        "mastered": 0,
    }

    total_reviews = 0

    for mistake in mistakes:
        total_reviews += mistake.review_count or 0

        if mistake.status in status_distribution:
            status_distribution[mistake.status] += 1

    knowledge_statistics = get_knowledge_point_statistics(
        db,
        user_id,
    )

    recorded_review_count = (
        db.query(MistakeReviewRecord)
        .filter(MistakeReviewRecord.user_id == user_id)
        .count()
    )

    return {
        "user_id": user_id,
        "total_mistakes": len(mistakes),
        "total_reviews": total_reviews,
        "recorded_review_count": recorded_review_count,
        "mastered_mistakes": status_distribution["mastered"],
        "total_knowledge_points": (
            knowledge_statistics["total_knowledge_points"]
        ),
        "weak_knowledge_points": (
            knowledge_statistics["weak_knowledge_points"]
        ),
        "status_distribution": status_distribution,
        "knowledge_points": knowledge_statistics["items"],
    }


def get_learning_trends(
    db: Session,
    user_id: str,
    days: int = 30,
    granularity: str = "day",
) -> dict:
    """
    获取用户的学习趋势。

    granularity:
        day: 按天统计
        week: 按周统计
    """

    if granularity not in ("day", "week"):
        raise ValueError("统计粒度必须为 day 或 week")

    if not 7 <= days <= 365:
        raise ValueError("统计天数必须在 7 到 365 之间")

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)

    start_datetime = datetime.combine(
        start_date,
        datetime.min.time(),
    )

    end_datetime = datetime.combine(
        end_date + timedelta(days=1),
        datetime.min.time(),
    )

    # 初始化统计时间区间
    def get_bucket(value: date) -> date:
        if granularity == "week":
            return value - timedelta(days=value.weekday())
        return value

    first_bucket = get_bucket(start_date)
    last_bucket = get_bucket(end_date)

    statistics = {}

    current_bucket = first_bucket

    step = timedelta(days=7 if granularity == "week" else 1)

    while current_bucket <= last_bucket:
        statistics[current_bucket] = {
            "date": current_bucket.isoformat(),
            "review_count": 0,
            "mastered_review_count": 0,
            "new_mistake_count": 0,
        }

        current_bucket += step

    # 获取指定用户的复习历史
    review_records = (
        db.query(MistakeReviewRecord)
        .filter(
            MistakeReviewRecord.user_id == user_id,
            MistakeReviewRecord.reviewed_at >= start_datetime,
            MistakeReviewRecord.reviewed_at < end_datetime,
        )
        .all()
    )

    for record in review_records:
        bucket = get_bucket(record.reviewed_at.date())

        if bucket not in statistics:
            continue

        statistics[bucket]["review_count"] += 1

        if record.status == "mastered":
            statistics[bucket]["mastered_review_count"] += 1

    # 获取指定用户在统计时间内新增的错题
    new_mistakes = (
        db.query(Mistake)
        .filter(
            Mistake.user_id == user_id,
            Mistake.created_at >= start_datetime,
            Mistake.created_at < end_datetime,
        )
        .all()
    )

    for mistake in new_mistakes:
        bucket = get_bucket(mistake.created_at.date())

        if bucket in statistics:
            statistics[bucket]["new_mistake_count"] += 1

    return {
        "user_id": user_id,
        "granularity": granularity,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": days,
        "items": list(statistics.values()),
    }