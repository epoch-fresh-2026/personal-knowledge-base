import pytest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base
from modules.ingest.domain.models import User
from shared.user_context import get_current_user


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(
        bind=engine,
        tables=[User.__table__],
    )

    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    session = TestingSession()

    session.add_all([
        User(id="u_zhangsan", nickname="张三"),
        User(id="u_lisi", nickname="李四"),
    ])
    session.commit()

    yield session

    session.close()
    engine.dispose()


def test_get_existing_user(db):
    user = get_current_user(
        user_id="u_zhangsan",
        db=db,
    )

    assert user.id == "u_zhangsan"
    assert user.nickname == "张三"


def test_get_another_existing_user(db):
    user = get_current_user(
        user_id="u_lisi",
        db=db,
    )

    assert user.id == "u_lisi"
    assert user.nickname == "李四"


def test_reject_nonexistent_user(db):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(
            user_id="u_unknown",
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "用户不存在"


def test_reject_invalid_user_id_format(db):
    """格式错误的用户 ID 返回 400（区别于不存在用户的 404）。"""
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(
            user_id="not-a-valid-id",
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "用户 ID 格式无效"
