from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base
from modules.ingest.domain.models import (
    User,
    Mistake,
    MistakeReviewRecord,
)
from modules.mistake.service.analytics_service import (
    get_learning_overview,
    get_learning_trends,
)


@pytest.fixture
def db():
    """创建独立的 SQLite 内存测试数据库。"""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            Mistake.__table__,
            MistakeReviewRecord.__table__,
        ],
    )

    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    session = TestingSession()

    yield session

    session.close()
    engine.dispose()


def add_user(db, user_id):
    db.add(
        User(
            id=user_id,
            nickname=user_id,
        )
    )


def add_mistake(
    db,
    mistake_id,
    user_id,
    status="pending",
    review_count=0,
    knowledge_points="",
    created_at=None,
):
    db.add(
        Mistake(
            id=mistake_id,
            user_id=user_id,
            question=f"测试题目 {mistake_id}",
            correct_answer="正确答案",
            wrong_answer="错误答案",
            error_reason="测试原因",
            knowledge_points=knowledge_points,
            status=status,
            review_count=review_count,
            created_at=created_at or datetime.utcnow(),
        )
    )


def add_review_record(
    db,
    record_id,
    mistake_id,
    user_id,
    status,
    reviewed_at,
):
    db.add(
        MistakeReviewRecord(
            id=record_id,
            mistake_id=mistake_id,
            user_id=user_id,
            status=status,
            reviewed_at=reviewed_at,
        )
    )


def test_learning_overview(db):
    """测试学习数据概览及知识点统计。"""

    add_user(db, "u_test")

    add_mistake(
        db,
        "m1",
        "u_test",
        status="pending",
        review_count=2,
        knowledge_points="导数, 函数",
    )

    add_mistake(
        db,
        "m2",
        "u_test",
        status="reviewing",
        review_count=3,
        knowledge_points="导数、极限",
    )

    add_mistake(
        db,
        "m3",
        "u_test",
        status="mastered",
        review_count=4,
        knowledge_points="函数",
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    add_review_record(
        db, "r1", "m1", "u_test", "reviewing", now
    )

    add_review_record(
        db, "r2", "m2", "u_test", "mastered", now
    )

    db.commit()

    result = get_learning_overview(db, "u_test")

    assert result["user_id"] == "u_test"
    assert result["total_mistakes"] == 3
    assert result["total_reviews"] == 9
    assert result["recorded_review_count"] == 2
    assert result["mastered_mistakes"] == 1

    assert result["status_distribution"] == {
        "pending": 1,
        "reviewing": 1,
        "mastered": 1,
    }

    assert result["total_knowledge_points"] == 3
    assert result["weak_knowledge_points"] == 3


def test_daily_learning_trends(db):
    """测试每日复习次数和新增错题数量。"""

    add_user(db, "u_daily")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now.date()
    yesterday = today - timedelta(days=1)

    today_time = datetime.combine(
        today,
        datetime.min.time(),
    ) + timedelta(hours=12)

    yesterday_time = datetime.combine(
        yesterday,
        datetime.min.time(),
    ) + timedelta(hours=12)

    add_mistake(
        db,
        "m_today",
        "u_daily",
        created_at=today_time,
    )

    add_mistake(
        db,
        "m_yesterday",
        "u_daily",
        created_at=yesterday_time,
    )

    add_review_record(
        db, "r1", "m_today", "u_daily", "reviewing", today_time
    )

    add_review_record(
        db, "r2", "m_today", "u_daily", "mastered", today_time
    )

    add_review_record(
        db, "r3", "m_yesterday", "u_daily", "reviewing",
        yesterday_time
    )

    db.commit()

    result = get_learning_trends(
        db,
        "u_daily",
        days=7,
        granularity="day",
    )

    assert result["granularity"] == "day"
    assert result["days"] == 7

    items = {
        item["date"]: item
        for item in result["items"]
    }

    assert len(items) == 7

    today_data = items[today.isoformat()]
    yesterday_data = items[yesterday.isoformat()]

    assert today_data["review_count"] == 2
    assert today_data["mastered_review_count"] == 1
    assert today_data["new_mistake_count"] == 1

    assert yesterday_data["review_count"] == 1
    assert yesterday_data["mastered_review_count"] == 0
    assert yesterday_data["new_mistake_count"] == 1


def test_weekly_learning_trends(db):
    """测试每周复习次数聚合。"""

    add_user(db, "u_weekly")

    today = datetime.now(timezone.utc).date()

    # 选择本周内的一天
    target_day = today - timedelta(
        days=min(today.weekday(), 1)
    )

    review_time = datetime.combine(
        target_day,
        datetime.min.time(),
    ) + timedelta(hours=12)

    add_mistake(
        db,
        "m_weekly",
        "u_weekly",
        created_at=review_time,
    )

    add_review_record(
        db, "r1", "m_weekly", "u_weekly", "reviewing",
        review_time
    )

    add_review_record(
        db,
        "r2",
        "m_weekly",
        "u_weekly",
        "mastered",
        review_time + timedelta(minutes=10),
    )

    db.commit()

    result = get_learning_trends(
        db,
        "u_weekly",
        days=7,
        granularity="week",
    )

    assert result["granularity"] == "week"

    items = {
        item["date"]: item
        for item in result["items"]
    }

    week_start = (
        target_day - timedelta(days=target_day.weekday())
    ).isoformat()

    assert items[week_start]["review_count"] == 2
    assert items[week_start]["mastered_review_count"] == 1


def test_analytics_user_isolation(db):
    """测试不同用户的统计数据相互隔离。"""

    add_user(db, "u_user1")
    add_user(db, "u_user2")

    add_mistake(
        db,
        "m_user1",
        "u_user1",
        review_count=5,
    )

    add_mistake(
        db,
        "m_user2",
        "u_user2",
        review_count=2,
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    add_review_record(
        db,
        "r_user1",
        "m_user1",
        "u_user1",
        "reviewing",
        now,
    )

    add_review_record(
        db,
        "r_user2",
        "m_user2",
        "u_user2",
        "mastered",
        now,
    )

    db.commit()

    result1 = get_learning_overview(db, "u_user1")
    result2 = get_learning_overview(db, "u_user2")

    assert result1["total_mistakes"] == 1
    assert result1["total_reviews"] == 5
    assert result1["recorded_review_count"] == 1

    assert result2["total_mistakes"] == 1
    assert result2["total_reviews"] == 2
    assert result2["recorded_review_count"] == 1

    assert result1["mastered_mistakes"] == 0
    assert result2["mastered_mistakes"] == 0


def test_invalid_trend_parameters(db):
    """测试无效统计参数。"""

    with pytest.raises(ValueError):
        get_learning_trends(
            db,
            "u_test",
            days=5,
            granularity="day",
        )

    with pytest.raises(ValueError):
        get_learning_trends(
            db,
            "u_test",
            days=30,
            granularity="month",
        )