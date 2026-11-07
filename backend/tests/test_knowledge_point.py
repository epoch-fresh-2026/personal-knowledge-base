import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base
from modules.ingest.domain.models import User, Mistake
from modules.mistake.service.knowledge_point_service import (
    split_knowledge_points,
    get_knowledge_point_statistics,
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


def test_split_knowledge_points():
    """测试多种分隔符、空白和重复知识点。"""

    result = split_knowledge_points(
        " 导数 、 函数极限，导数;连续性； Python \n"
    )

    assert result == [
        "导数",
        "函数极限",
        "连续性",
        "Python",
    ]

    assert split_knowledge_points("") == []
    assert split_knowledge_points(None) == []


def test_knowledge_point_statistics(db):
    """测试知识点数量、复习状态和薄弱率统计。"""

    db.add_all([
        User(id="u_test1", nickname="测试用户1"),
        User(id="u_test2", nickname="测试用户2"),
    ])

    db.add_all([
        Mistake(
            id="m1",
            user_id="u_test1",
            question="错题1",
            knowledge_points="导数、函数极限",
            status="pending",
            review_count=1,
        ),
        Mistake(
            id="m2",
            user_id="u_test1",
            question="错题2",
            knowledge_points="导数，连续性",
            status="reviewing",
            review_count=2,
        ),
        Mistake(
            id="m3",
            user_id="u_test1",
            question="错题3",
            knowledge_points="导数;函数极限",
            status="mastered",
            review_count=3,
        ),
        Mistake(
            id="m4",
            user_id="u_test2",
            question="其他用户的错题",
            knowledge_points="导数",
            status="pending",
            review_count=10,
        ),
    ])

    db.commit()

    result = get_knowledge_point_statistics(db, "u_test1")

    assert result["user_id"] == "u_test1"
    assert result["total_knowledge_points"] == 3
    assert result["weak_knowledge_points"] == 3

    items = {
        item["knowledge_point"]: item
        for item in result["items"]
    }

    # 导数：3道错题，2道尚未掌握
    derivative = items["导数"]

    assert derivative["total_mistakes"] == 3
    assert derivative["pending_count"] == 1
    assert derivative["reviewing_count"] == 1
    assert derivative["mastered_count"] == 1
    assert derivative["unmastered_count"] == 2
    assert derivative["weak_rate"] == 0.6667
    assert derivative["review_count"] == 6
    assert derivative["status"] == "weak"

    # 函数极限：2道错题
    limit = items["函数极限"]

    assert limit["total_mistakes"] == 2
    assert limit["unmastered_count"] == 1
    assert limit["weak_rate"] == 0.5
    assert limit["review_count"] == 4

    # 连续性：1道错题
    continuity = items["连续性"]

    assert continuity["total_mistakes"] == 1
    assert continuity["reviewing_count"] == 1
    assert continuity["weak_rate"] == 1.0


def test_knowledge_point_user_isolation(db):
    """测试不同用户的知识点统计互相隔离。"""

    db.add_all([
        User(id="u_test1", nickname="测试用户1"),
        User(id="u_test2", nickname="测试用户2"),
    ])

    db.add_all([
        Mistake(
            id="m1",
            user_id="u_test1",
            question="用户1的错题",
            knowledge_points="Python",
            status="pending",
            review_count=1,
        ),
        Mistake(
            id="m2",
            user_id="u_test2",
            question="用户2的错题",
            knowledge_points="Python",
            status="mastered",
            review_count=5,
        ),
    ])

    db.commit()

    result1 = get_knowledge_point_statistics(db, "u_test1")
    result2 = get_knowledge_point_statistics(db, "u_test2")

    assert result1["items"][0]["total_mistakes"] == 1
    assert result1["items"][0]["review_count"] == 1

    assert result2["items"][0]["total_mistakes"] == 1
    assert result2["items"][0]["review_count"] == 5

    assert result1["items"][0]["status"] == "weak"
    assert result2["items"][0]["status"] == "mastered"


def test_empty_knowledge_point_statistics(db):
    """测试没有错题时的返回结果。"""

    result = get_knowledge_point_statistics(db, "u_empty")

    assert result["total_knowledge_points"] == 0
    assert result["weak_knowledge_points"] == 0
    assert result["items"] == []