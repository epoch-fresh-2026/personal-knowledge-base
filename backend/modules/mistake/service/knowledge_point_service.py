import re

from sqlalchemy.orm import Session

from modules.ingest.domain.models import Mistake


def split_knowledge_points(value: str | None) -> list[str]:
    """
    拆分知识点，兼容中英文逗号、顿号、分号和换行。
    去除空白项和重复知识点。
    """

    if not value or not value.strip():
        return []

    parts = re.split(r"[,，、;；\r\n]+", value)

    results = []
    seen = set()

    for part in parts:
        point = " ".join(part.strip().split())

        if not point:
            continue

        key = point.casefold()

        if key in seen:
            continue

        seen.add(key)
        results.append(point)

    return results


def get_knowledge_point_statistics(
    db: Session,
    user_id: str
) -> dict:
    """
    统计指定用户的知识点掌握情况。

    薄弱率 = 未掌握错题数 / 错题总数
    未掌握错题 = 待复习 + 复习中
    """

    mistakes = (
        db.query(Mistake)
        .filter(Mistake.user_id == user_id)
        .all()
    )

    statistics = {}

    for mistake in mistakes:
        knowledge_points = split_knowledge_points(
            mistake.knowledge_points
        )

        for point in knowledge_points:

            key = point.casefold()

            if key not in statistics:
                statistics[key] = {
                    "knowledge_point": point,
                    "total_mistakes": 0,
                    "pending_count": 0,
                    "reviewing_count": 0,
                    "mastered_count": 0,
                    "review_count": 0,
                }

            item = statistics[key]

            item["total_mistakes"] += 1
            item["review_count"] += mistake.review_count or 0

            if mistake.status == "pending":
                item["pending_count"] += 1

            elif mistake.status == "reviewing":
                item["reviewing_count"] += 1

            elif mistake.status == "mastered":
                item["mastered_count"] += 1

            else:
                # 未知状态暂按待复习处理，避免将其误判为已掌握
                item["pending_count"] += 1

    items = []

    for item in statistics.values():

        unmastered_count = (
            item["pending_count"]
            + item["reviewing_count"]
        )

        weak_rate = (
            unmastered_count / item["total_mistakes"]
            if item["total_mistakes"] > 0
            else 0
        )

        item["unmastered_count"] = unmastered_count
        item["weak_rate"] = round(weak_rate, 4)

        item["status"] = (
            "weak" if unmastered_count > 0 else "mastered"
        )

        items.append(item)

    # 优先展示未掌握错题较多、薄弱率较高的知识点
    items.sort(
        key=lambda item: (
            -item["unmastered_count"],
            -item["weak_rate"],
            -item["total_mistakes"],
            item["knowledge_point"].casefold(),
        )
    )

    return {
        "user_id": user_id,
        "total_knowledge_points": len(items),
        "weak_knowledge_points": sum(
            1 for item in items if item["status"] == "weak"
        ),
        "items": items,
    }