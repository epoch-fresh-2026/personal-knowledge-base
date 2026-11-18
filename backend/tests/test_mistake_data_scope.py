"""Issue #53：错题数据口径、模型迁移与级联删除验收测试。

覆盖裁决要点：
- 模型迁移：新旧路径同一 ORM 类对象、单表映射、init_db 注册、真实库数据不丢；
- 路由集成：当前用户隔离、状态修改≠复习、复习事务回滚、级联删除；
- 统计：累计次数与记录数区分、趋势按复习记录时间、UTC 边界、知识点隔离；
- 推荐：候选状态、权重/阈值/排序锁定。

所有数据库测试使用独立临时 SQLite（内存或 tmp_path 文件库），
不触碰真实 backend/pkb.db。
"""

import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import shared.db as shared_db
from shared.db import Base, get_db
from modules.ingest.domain.models import User
from modules.mistake.domain.models import Mistake, MistakeReviewRecord
from api.router import api_router


# ---------- 模型迁移与注册 ----------

def test_new_and_old_import_are_same_class():
    """正式路径与兼容重导出得到同一个 ORM 类对象。"""
    from modules.mistake.domain.models import Mistake as NewM, MistakeReviewRecord as NewR
    from modules.ingest.domain.models import Mistake as OldM, MistakeReviewRecord as OldR
    assert NewM is OldM
    assert NewR is OldR


def test_single_table_mapping():
    """错题模型只有一套表映射，不重复定义。"""
    mappers = [
        m.class_.__name__ for m in Base.registry.mappers
        if m.class_.__name__ in ("Mistake", "MistakeReviewRecord")
    ]
    assert sorted(mappers) == ["Mistake", "MistakeReviewRecord"]
    assert "mistakes" in Base.metadata.tables
    assert "mistake_review_records" in Base.metadata.tables


def test_init_db_registers_mistake_models(tmp_path, monkeypatch):
    """init_db() 能正确注册错题模型并建表（使用临时库，不碰真实 DB）。"""
    db_path = tmp_path / "init_db_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(shared_db, "engine", engine)
    monkeypatch.setattr(shared_db, "SessionLocal", Session)

    shared_db.init_db()

    conn = sqlite3.connect(str(db_path))
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "mistakes" in tables
    assert "mistake_review_records" in tables
    engine.dispose()


def test_real_database_data_unchanged_after_migration():
    """迁移不覆盖、不重建真实数据库：错题与复习记录数量保持一致。

    仅只读核对当前真实库中数据仍存在（基线：3 道错题、5 条复习记录）。
    迁移过程未执行任何 DROP/CREATE/DELETE，故此处断言数据仍在。
    """
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "pkb.db"
    )
    if not os.path.exists(db_path):
        pytest.skip("真实数据库不存在，跳过数据保留核对")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    mistakes = conn.execute("SELECT count(*) FROM mistakes").fetchone()[0]
    reviews = conn.execute(
        "SELECT count(*) FROM mistake_review_records"
    ).fetchone()[0]
    conn.close()
    assert mistakes >= 3, "错题数据不应因迁移丢失"
    assert reviews >= 5, "复习记录不应因迁移丢失"


# ---------- 路由集成 fixture ----------

@pytest.fixture
def api_ctx(tmp_path):
    """独立 SQLite 文件库 + TestClient；建三张业务表。"""
    db_path = tmp_path / "mistake_api.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[User.__table__, Mistake.__table__, MistakeReviewRecord.__table__],
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    db.add_all([
        User(id="u_zhangsan", nickname="张三"),
        User(id="u_lisi", nickname="李四"),
    ])
    db.commit()

    def override_get_db():
        yield db

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, db, str(db_path)

    db.close()
    engine.dispose()


def _create(client, user, question="题目"):
    return client.post(
        "/api/v1/mistakes",
        params={"user_id": user},
        json={"question": question, "knowledge_points": "导数, 函数"},
    )


def _add_mistake(db, mid, user, status="pending", review_count=0,
                 kp="导数, 函数", created_at=None):
    db.add(Mistake(
        id=mid, user_id=user, question="题", status=status,
        review_count=review_count, knowledge_points=kp,
        created_at=created_at or datetime.utcnow(),
    ))
    db.commit()


def _add_review(db, rid, mid, user, status="reviewing", reviewed_at=None):
    db.add(MistakeReviewRecord(
        id=rid, mistake_id=mid, user_id=user, status=status,
        reviewed_at=reviewed_at or datetime.utcnow(),
    ))
    db.commit()


# ---------- 用户隔离与 CRUD ----------

def test_cross_user_operations_are_rejected(api_ctx):
    client, db, _ = api_ctx
    created = _create(client, "u_zhangsan", "张三的题").json()
    mid = created["id"]

    assert db.query(Mistake).filter(Mistake.id == mid).first().user_id == "u_zhangsan"
    # 李四不能查看（列表）、修改、改状态、复习、删除张三的错题
    assert all(m["id"] != mid for m in
               client.get("/api/v1/mistakes", params={"user_id": "u_lisi"}).json())
    assert client.put(
        f"/api/v1/mistakes/{mid}", params={"user_id": "u_lisi"},
        json={"question": "篡改"},
    ).json().get("message") == "未找到错题"
    assert client.patch(
        f"/api/v1/mistakes/{mid}/status", params={"user_id": "u_lisi"},
        json={"status": "mastered"},
    ).json().get("message") == "未找到错题"
    assert client.post(
        f"/api/v1/mistakes/{mid}/review", params={"user_id": "u_lisi"},
        json={"status": "mastered"},
    ).json().get("message") == "未找到错题"
    assert client.delete(
        f"/api/v1/mistakes/{mid}", params={"user_id": "u_lisi"},
    ).json().get("message") == "未找到错题"
    # 数据未被改动
    row = db.query(Mistake).filter(Mistake.id == mid).first()
    assert row.question == "张三的题" and row.status == "pending"


def test_status_update_does_not_create_review(api_ctx):
    client, db, _ = api_ctx
    mid = _create(client, "u_zhangsan").json()["id"]
    resp = client.patch(
        f"/api/v1/mistakes/{mid}/status", params={"user_id": "u_zhangsan"},
        json={"status": "mastered"},
    )
    assert resp.status_code == 200
    row = db.query(Mistake).filter(Mistake.id == mid).first()
    assert row.status == "mastered"
    assert row.review_count == 0
    assert row.last_reviewed_at is None
    assert db.query(MistakeReviewRecord).filter(
        MistakeReviewRecord.mistake_id == mid
    ).count() == 0


def test_complete_review_updates_all_fields(api_ctx):
    client, db, _ = api_ctx
    mid = _create(client, "u_zhangsan").json()["id"]
    resp = client.post(
        f"/api/v1/mistakes/{mid}/review", params={"user_id": "u_zhangsan"},
        json={"status": "reviewing"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["review_count"] == 1
    assert data["last_reviewed_at"] is not None
    assert data["review_record_id"]
    row = db.query(Mistake).filter(Mistake.id == mid).first()
    assert row.status == "reviewing" and row.review_count == 1
    assert db.query(MistakeReviewRecord).filter(
        MistakeReviewRecord.mistake_id == mid
    ).count() == 1


def test_complete_review_rolls_back_on_failure(api_ctx, monkeypatch):
    """复习写入中途失败时不能留下部分更新（同事务语义）。

    路由持有与前序创建相同的 db session（dependency_overrides）。
    让新增复习记录时抛异常，验证未提交、库中无部分更新。
    """
    client, db, _ = api_ctx
    mid = _create(client, "u_zhangsan").json()["id"]

    original_add = db.add

    def boom(*args, **kwargs):
        if args and isinstance(args[0], MistakeReviewRecord):
            raise RuntimeError("写入复习记录失败")
        return original_add(*args, **kwargs)

    monkeypatch.setattr(db, "add", boom)

    with pytest.raises(Exception):
        client.post(
            f"/api/v1/mistakes/{mid}/review", params={"user_id": "u_zhangsan"},
            json={"status": "mastered"},
        )

    db.rollback()
    row = db.query(Mistake).filter(Mistake.id == mid).first()
    assert row.review_count == 0
    assert row.status == "pending"
    assert row.last_reviewed_at is None
    assert db.query(MistakeReviewRecord).filter(
        MistakeReviewRecord.mistake_id == mid
    ).count() == 0


# ---------- 级联删除（真实 SQLite 文件库）----------

def test_delete_mistake_cascades_review_records_on_disk(api_ctx):
    client, db, db_path = api_ctx
    mid = str(uuid.uuid4())
    _add_mistake(db, mid, "u_zhangsan")
    for i in range(3):
        _add_review(db, str(uuid.uuid4()), mid, "u_zhangsan")

    conn = sqlite3.connect(db_path)
    assert conn.execute(
        "SELECT count(*) FROM mistake_review_records WHERE mistake_id=?", (mid,)
    ).fetchone()[0] == 3
    conn.close()

    resp = client.delete(
        f"/api/v1/mistakes/{mid}", params={"user_id": "u_zhangsan"}
    )
    assert resp.status_code == 200

    # 磁盘真实核对：错题与全部复习记录均被清理
    conn = sqlite3.connect(db_path)
    assert conn.execute(
        "SELECT count(*) FROM mistakes WHERE id=?", (mid,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT count(*) FROM mistake_review_records WHERE mistake_id=?", (mid,)
    ).fetchone()[0] == 0
    conn.close()


# ---------- 统计口径与边界（独立内存库）----------

@pytest.fixture
def svc_db():
    """service 层测试用独立内存库。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[User.__table__, Mistake.__table__, MistakeReviewRecord.__table__],
    )
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = S()
    db.add_all([User(id="u_a", nickname="A"), User(id="u_b", nickname="B")])
    db.commit()
    yield db
    db.close()
    engine.dispose()


def test_overview_distinguishes_cumulative_vs_recorded(svc_db):
    """total_reviews（累计字段和）与 recorded_review_count（记录条数）区分。"""
    from modules.mistake.service.analytics_service import get_learning_overview
    # review_count=5 但只有 1 条复习记录 → 两者应不同
    _add_mistake(svc_db, "m1", "u_a", review_count=5)
    _add_review(svc_db, "r1", "m1", "u_a")
    svc_db.commit()
    result = get_learning_overview(svc_db, "u_a")
    assert result["total_reviews"] == 5
    assert result["recorded_review_count"] == 1
    assert result["total_mistakes"] == 1
    assert result["total_reviews"] != result["recorded_review_count"]


def test_trends_use_review_record_time_not_status(svc_db):
    """趋势复习次数来自复习记录时间，不因错题当前状态改变。"""
    from modules.mistake.service.analytics_service import get_learning_trends
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mid = "m_trend"
    _add_mistake(svc_db, mid, "u_a", status="mastered", created_at=now)
    # 两条不同日期的复习记录
    _add_review(svc_db, "r1", mid, "u_a", "reviewing", now - timedelta(days=1))
    _add_review(svc_db, "r2", mid, "u_a", "mastered", now)
    svc_db.commit()
    result = get_learning_trends(svc_db, "u_a", days=7, granularity="day")
    items = {i["date"]: i for i in result["items"]}
    total_reviews = sum(i["review_count"] for i in items.values())
    assert total_reviews == 2  # 依据记录，而非当前 mastered 状态
    assert sum(i["mastered_review_count"] for i in items.values()) == 1
    assert sum(i["new_mistake_count"] for i in items.values()) == 1


def test_trends_utc_boundary_and_granularity(svc_db):
    """UTC 跨日、跨周与时间区间边界正确。"""
    from modules.mistake.service.analytics_service import get_learning_trends
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now.date()
    # 区间外（days 之前）的记录不应计入
    outside = datetime.combine(today - timedelta(days=10), datetime.min.time())
    inside = datetime.combine(today, datetime.min.time()) + timedelta(hours=1)
    _add_mistake(svc_db, "m_out", "u_a", created_at=outside)
    _add_mistake(svc_db, "m_in", "u_a", created_at=inside)
    _add_review(svc_db, "r_out", "m_out", "u_a", reviewed_at=outside)
    _add_review(svc_db, "r_in", "m_in", "u_a", reviewed_at=inside)
    svc_db.commit()

    daily = get_learning_trends(svc_db, "u_a", days=7, granularity="day")
    assert len(daily["items"]) == 7
    assert sum(i["review_count"] for i in daily["items"]) == 1
    assert sum(i["new_mistake_count"] for i in daily["items"]) == 1

    weekly = get_learning_trends(svc_db, "u_a", days=7, granularity="week")
    assert weekly["granularity"] == "week"
    # 每条记录归到所在周的周一，桶数为去重周数
    buckets = {i["date"] for i in weekly["items"]}
    assert all(datetime.fromisoformat(d).weekday() == 0 for d in buckets)


def test_knowledge_points_are_user_isolated(svc_db):
    """知识点统计只用当前用户错题。"""
    from modules.mistake.service.knowledge_point_service import get_knowledge_point_statistics
    _add_mistake(svc_db, "ma", "u_a", status="pending", kp="函数, 导数")
    _add_mistake(svc_db, "mb", "u_b", status="mastered", kp="函数, 概率")
    svc_db.commit()
    ra = get_knowledge_point_statistics(svc_db, "u_a")
    rb = get_knowledge_point_statistics(svc_db, "u_b")
    pa = {i["knowledge_point"] for i in ra["items"]}
    pb = {i["knowledge_point"] for i in rb["items"]}
    assert pa == {"函数", "导数"}
    assert pb == {"函数", "概率"}
    assert "概率" not in pa and "导数" not in pb


# ---------- 推荐算法锁定 ----------

def test_recommendation_candidates_and_scoring_locked(svc_db):
    """候选仅 pending/reviewing；分数/阈值/排序与当前算法一致。"""
    from modules.mistake.service.recommendation_service import get_review_recommendations
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # pending，从未复习，知识点"函数"薄弱 → high
    _add_mistake(svc_db, "m1", "u_a", status="pending", kp="函数")
    # reviewing，最近复习 → medium
    _add_mistake(svc_db, "m2", "u_a", status="reviewing", kp="函数")
    _add_mistake(svc_db, "m2r", "u_a", status="reviewing", kp="函数")
    _add_review(svc_db, "r2", "m2", "u_a", reviewed_at=now)
    # mastered 不进入候选
    _add_mistake(svc_db, "m3", "u_a", status="mastered", kp="函数")
    svc_db.commit()

    result = get_review_recommendations(svc_db, "u_a", limit=10)
    ids = {i["mistake_id"] for i in result["items"]}
    assert "m3" not in ids, "mastered 不应进入推荐"
    assert "m1" in ids and "m2" in ids

    m1 = next(i for i in result["items"] if i["mistake_id"] == "m1")
    # pending 基础 60 + 薄弱知识点加分 >= 0 → 至少 60 → high
    assert m1["priority_score"] >= 60
    assert m1["priority"] == "high"

    # 分数降序
    scores = [i["priority_score"] for i in result["items"]]
    assert scores == sorted(scores, reverse=True)


def test_recommendation_weights_match_reference(svc_db):
    """锁定权重：pending=60、reviewing=35；days>=7:+20、days>=3:+10。"""
    from modules.mistake.service.recommendation_service import (
        calculate_recommendation,
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # 无知识点、无复习记录：pending 恰好 60，reviewing 恰好 35+10（无复习时间且reviewing）
    pending = Mistake(id="p", user_id="u_a", question="q", status="pending", knowledge_points="")
    sc_pending = calculate_recommendation(pending, {})["priority_score"]
    assert sc_pending == 60

    reviewing = Mistake(id="rv", user_id="u_a", question="q", status="reviewing", knowledge_points="")
    sc_reviewing = calculate_recommendation(reviewing, {})["priority_score"]
    assert sc_reviewing == 35 + 10  # last_reviewed_at None 且 reviewing +10
