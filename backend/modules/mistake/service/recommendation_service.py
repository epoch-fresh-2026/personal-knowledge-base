from datetime import datetime, timezone

from sqlalchemy.orm import Session

from modules.ingest.domain.models import Mistake
from modules.mistake.service.knowledge_point_service import (
    split_knowledge_points,
    get_knowledge_point_statistics,
)


def calculate_days_since_review(
    last_reviewed_at: datetime | None,
) -> int | None:
    """计算距离最近一次复习经过的天数。"""

    if last_reviewed_at is None:
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 兼容带时区和不带时区的数据库时间
    if last_reviewed_at.tzinfo is not None:
        last_reviewed_at = (
            last_reviewed_at.astimezone(timezone.utc)
            .replace(tzinfo=None)
        )

    return max(0, (now - last_reviewed_at).days)


def calculate_recommendation(
    mistake: Mistake,
    weak_points: dict,
) -> dict:
    """计算单道错题的推荐优先级及推荐理由。"""

    score = 0
    reasons = []

    # 1. 根据复习状态确定基础分
    if mistake.status == "pending":
        score += 60
        reasons.append("该错题目前处于待复习状态，建议优先完成复习。")

    elif mistake.status == "reviewing":
        score += 35
        reasons.append("该错题仍处于复习中，可以继续巩固。")

    # 2. 拆分关联知识点
    knowledge_points = split_knowledge_points(
        mistake.knowledge_points
    )

    matched_weak_points = []

    for point in knowledge_points:
        statistics = weak_points.get(point.casefold())

        if statistics and statistics["status"] == "weak":
            matched_weak_points.append(statistics)

    # 3. 根据薄弱知识点调整优先级
    if matched_weak_points:
        max_weak_rate = max(
            item["weak_rate"]
            for item in matched_weak_points
        )

        score += round(max_weak_rate * 20)

        for item in matched_weak_points[:3]:
            reasons.append(
                f"关联知识点「{item['knowledge_point']}」"
                f"仍有 {item['unmastered_count']} 道未掌握错题，"
                f"薄弱率为 {item['weak_rate']:.0%}。"
            )

    # 4. 根据最近复习时间调整优先级
    days = calculate_days_since_review(
        mistake.last_reviewed_at
    )

    if days is None:
        reasons.append("该错题尚未记录最近一次复习时间。")
        if mistake.status == "reviewing":
            score += 10

    elif days >= 7:
        score += 20
        reasons.append(f"距离上次复习已过去 {days} 天，建议重新巩固。")

    elif days >= 3:
        score += 10
        reasons.append(f"距离上次复习已过去 {days} 天，可以安排再次复习。")

    # 5. 确定推荐等级
    if score >= 60:
        priority = "high"
    elif score >= 35:
        priority = "medium"
    else:
        priority = "low"

    return {
        "mistake_id": mistake.id,
        "question": mistake.question,
        "knowledge_points": knowledge_points,
        "status": mistake.status,
        "review_count": mistake.review_count or 0,
        "last_reviewed_at": (
            mistake.last_reviewed_at.isoformat()
            if mistake.last_reviewed_at else None
        ),
        "days_since_last_review": days,
        "priority": priority,
        "priority_score": score,
        "reasons": reasons,
    }


def get_review_recommendations(
    db: Session,
    user_id: str,
    limit: int = 10,
) -> dict:
    """
    生成当前用户的个性化复习建议。

    仅推荐待复习和复习中的错题。
    已掌握的错题不进入推荐列表。
    """

    limit = max(1, min(limit, 50))

    # 1. 获取当前用户的错题
    mistakes = (
        db.query(Mistake)
        .filter(
            Mistake.user_id == user_id,
            Mistake.status.in_(("pending", "reviewing")),
        )
        .all()
    )

    # 2. 获取当前用户的薄弱知识点
    statistics = get_knowledge_point_statistics(
        db,
        user_id,
    )

    weak_points = {
        item["knowledge_point"].casefold(): item
        for item in statistics["items"]
    }

    # 3. 生成每道错题的推荐结果
    recommendations = [
        calculate_recommendation(mistake, weak_points)
        for mistake in mistakes
    ]

    # 4. 按优先级分数排序
    recommendations.sort(
        key=lambda item: (
            -item["priority_score"],
            -(item["days_since_last_review"] or 0),
            item["mistake_id"],
        )
    )

    total = len(recommendations)

    return {
        "user_id": user_id,
        "total_recommendations": total,
        "returned_count": min(total, limit),
        "items": recommendations[:limit],
    }