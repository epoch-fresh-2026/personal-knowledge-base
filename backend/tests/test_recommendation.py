from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base
from modules.ingest.domain.models import User, Mistake
from modules.mistake.service.recommendation_service import (
    get_review_recommendations,
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
        tables=[User.__table__, Mistake.__table__],
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


def test_recommendation_priority_and_reasons(db):
    """测试推荐优先级、推荐理由和已掌握错题排除。"""

    db.add(User(id="u_test", nickname="测试用户"))

    # 待复习：基础分60 + 薄弱知识点加分20 = 80
    db.add(
        Mistake(
            id="m_pending",
            user_id="u_test",
            question="求导数",
            knowledge_points="导数",
            status="pending",
            review_count=0,
            last_reviewed_at=None,
        )
    )

    # 复习中：基础分35 + 薄弱知识点加分20
    # + 超过7天未复习加分20 = 75
    old_time = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(days=8)
    )

    db.add(
        Mistake(
            id="m_reviewing",
            user_id="u_test",
            question="求函数极限",
            knowledge_points="极限",
            status="reviewing",
            review_count=2,
            last_reviewed_at=old_time,
        )
    )

    # 函数知识点：1道复习中，9道已掌握
    # 薄弱率10%，复习中基础分35 + 2分 + 未记录复习时间10分 = 47
    db.add(
        Mistake(
            id="m_medium",
            user_id="u_test",
            question="函数综合题",
            knowledge_points="函数",
            status="reviewing",
            review_count=1,
            last_reviewed_at=None,
        )
    )

    for i in range(9):
        db.add(
            Mistake(
                id=f"m_mastered_{i}",
                user_id="u_test",
                question=f"已掌握错题{i}",
                knowledge_points="函数",
                status="mastered",
                review_count=3,
            )
        )

    # 已掌握的其他错题不应该进入推荐列表
    db.add(
        Mistake(
            id="m_excluded",
            user_id="u_test",
            question="已经掌握的知识",
            knowledge_points="积分",
            status="mastered",
            review_count=5,
        )
    )

    db.commit()

    result = get_review_recommendations(db, "u_test")

    assert result["total_recommendations"] == 3
    assert result["returned_count"] == 3

    items = result["items"]

    # 检查推荐排序
    assert [item["mistake_id"] for item in items] == [
        "m_pending",
        "m_reviewing",
        "m_medium",
    ]

    # 检查优先级和评分
    assert items[0]["priority"] == "high"
    assert items[0]["priority_score"] == 80

    assert items[1]["priority"] == "high"
    assert items[1]["priority_score"] == 75

    assert items[2]["priority"] == "medium"
    assert items[2]["priority_score"] == 47

    # 检查推荐理由
    assert any("待复习状态" in reason for reason in items[0]["reasons"])
    assert any("导数" in reason for reason in items[0]["reasons"])

    assert any("8 天" in reason for reason in items[1]["reasons"])

    assert any("函数" in reason for reason in items[2]["reasons"])

    # 已掌握错题不进入推荐列表
    recommended_ids = {
        item["mistake_id"] for item in items
    }

    assert "m_excluded" not in recommended_ids


def test_recommendation_user_isolation_and_limit(db):
    """测试用户数据隔离和推荐数量限制。"""

    db.add_all([
        User(id="u_test1", nickname="测试用户1"),
        User(id="u_test2", nickname="测试用户2"),
    ])

    for i in range(4):
        db.add(
            Mistake(
                id=f"m_user1_{i}",
                user_id="u_test1",
                question=f"用户1错题{i}",
                knowledge_points=f"知识点{i}",
                status="pending",
                review_count=0,
            )
        )

    db.add(
        Mistake(
            id="m_user2",
            user_id="u_test2",
            question="用户2错题",
            knowledge_points="其他知识点",
            status="pending",
            review_count=0,
        )
    )

    db.commit()

    result1 = get_review_recommendations(
        db,
        "u_test1",
        limit=2,
    )

    result2 = get_review_recommendations(
        db,
        "u_test2",
    )

    assert result1["total_recommendations"] == 4
    assert result1["returned_count"] == 2
    assert len(result1["items"]) == 2

    assert result2["total_recommendations"] == 1
    assert result2["items"][0]["mistake_id"] == "m_user2"

    assert all(
        item["mistake_id"].startswith("m_user1_")
        for item in result1["items"]
    )


def test_empty_recommendations(db):
    """测试没有待复习错题时的返回结果。"""

    db.add(
        User(id="u_empty", nickname="空用户")
    )
    db.commit()

    result = get_review_recommendations(db, "u_empty")

    assert result["user_id"] == "u_empty"
    assert result["total_recommendations"] == 0
    assert result["returned_count"] == 0
    assert result["items"] == []