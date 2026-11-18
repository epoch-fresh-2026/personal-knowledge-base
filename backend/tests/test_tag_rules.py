"""Issue #51：全局共享标签的创建者、关联与置顶规则验收测试（规则 B）。

覆盖验收标准：
- 创建者字段记录；名称规范化后全局唯一；
- 所有用户可查看/使用已有全局标签；
- 添加/移除关联校验当前用户对文档的管理权限；
- 标签关联文档查询按当前用户可访问范围（自有 OR 公开）过滤，并排除软删除；
- 仅创建者可删除；仍有关联时禁止删除并提示先解除关联；关联解除后可删；非创建者删除失败且数据不变；
- 置顶为全局共享状态，所有用户看到一致结果；
- 历史无创建者标签的迁移兼容。

使用独立内存 SQLite + dependency_overrides，不触碰真实数据库。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base, get_db
from modules.ingest.domain.models import User, Document
from modules.manage.domain.models import Tag, DocumentTag
from api.router import api_router


def _doc(doc_id, owner, title, public=False, deleted=False):
    return Document(
        id=doc_id,
        title=title,
        source_type="text",
        source_url=None,
        is_public=public,
        owner_id=owner,
        is_deleted=deleted,
    )


@pytest.fixture
def ctx():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()

    db.add_all([
        User(id="u_zhangsan", nickname="张三"),
        User(id="u_lisi", nickname="李四"),
    ])
    db.add_all([
        # 张三创建的标签
        Tag(id="tag_zs", name="Python", pinned=False, creator_id="u_zhangsan"),
        # 李四创建的标签
        Tag(id="tag_ls", name="数据库", pinned=True, creator_id="u_lisi"),
        # 历史标签：无创建者（迁移兼容）
        Tag(id="tag_legacy", name="旧标签", pinned=False, creator_id=None),
    ])
    db.add_all([
        _doc("zs_public", "u_zhangsan", "张三公开", public=True),
        _doc("zs_private", "u_zhangsan", "张三私有"),
        _doc("zs_deleted", "u_zhangsan", "张三已删", public=True, deleted=True),
        _doc("ls_public", "u_lisi", "李四公开", public=True),
        _doc("ls_private", "u_lisi", "李四私有"),
        _doc("ls_deleted", "u_lisi", "李四已删", public=True, deleted=True),
        _doc("ls_untagged", "u_lisi", "李四未打标文档", public=True),
    ])
    db.add_all([
        DocumentTag(document_id="zs_public", tag_id="tag_zs"),
        DocumentTag(document_id="zs_private", tag_id="tag_zs"),
        DocumentTag(document_id="zs_deleted", tag_id="tag_zs"),
        DocumentTag(document_id="ls_public", tag_id="tag_zs"),
        DocumentTag(document_id="ls_private", tag_id="tag_zs"),
        DocumentTag(document_id="ls_deleted", tag_id="tag_zs"),
    ])
    db.commit()

    def override_get_db():
        yield db

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c, db

    db.close()
    engine.dispose()


def _ids(resp):
    data = resp.json()
    return {item["id"] for item in data} if isinstance(data, list) else set()


# ---------- 创建：名称规范化、全局唯一、记录创建者 ----------

def test_create_tag_records_creator(ctx):
    client, db = ctx
    resp = client.post("/api/v1/tags", params={"user_id": "u_lisi"}, json={"name": "  新标签  "})
    assert resp.status_code == 200
    tag = db.query(Tag).filter(Tag.id == resp.json()["id"]).first()
    assert tag.name == "新标签"          # 首尾空白被去除
    assert tag.creator_id == "u_lisi"    # 记录创建者


def test_create_tag_empty_name_rejected(ctx):
    client, _ = ctx
    resp = client.post("/api/v1/tags", params={"user_id": "u_zhangsan"}, json={"name": "   "})
    assert resp.status_code == 400


def test_create_tag_normalized_duplicate_rejected(ctx):
    client, _ = ctx
    # 已有 "Python"；大小写/空白差异仍视为重复
    for dup in ["python", "  Python  ", "PYTHON"]:
        resp = client.post("/api/v1/tags", params={"user_id": "u_lisi"}, json={"name": dup})
        assert resp.status_code == 400


def test_all_users_can_view_and_use_global_tags(ctx):
    client, _ = ctx
    # 所有用户看到一致的全局标签列表
    zhang = _ids(client.get("/api/v1/tags"))
    # GET /tags 无 current_user 依赖，直接列出
    assert {"tag_zs", "tag_ls", "tag_legacy"} <= zhang
    # 李四可在自己的未打标文档上使用张三创建的标签
    resp = client.post(
        "/api/v1/documents/ls_untagged/tags/tag_zs",
        params={"user_id": "u_lisi"},
    )
    assert resp.status_code == 200


# ---------- 删除：创建者、非创建者、有关联、历史标签 ----------

def test_creator_can_delete_tag_without_relations(ctx):
    client, db = ctx
    # 先清空 tag_ls 的关联（它没有关联，直接删）
    resp = client.delete("/api/v1/tags/tag_ls", params={"user_id": "u_lisi"})
    assert resp.status_code == 200
    assert db.query(Tag).filter(Tag.id == "tag_ls").first() is None


def test_non_creator_cannot_delete_tag(ctx):
    client, db = ctx
    # tag_ls 由李四创建，张三不能删
    resp = client.delete("/api/v1/tags/tag_ls", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 404
    assert db.query(Tag).filter(Tag.id == "tag_ls").first() is not None


def test_delete_tag_with_relations_rejected(ctx):
    client, db = ctx
    # tag_zs 仍有多条文档关联，即使创建者张三也不能直接删
    links_before = db.query(DocumentTag).filter(DocumentTag.tag_id == "tag_zs").count()
    assert links_before > 0
    resp = client.delete("/api/v1/tags/tag_zs", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 404
    assert "解除关联" in resp.json()["detail"]
    # 标签仍在，且关联未被静默删除（删除前后数量一致）
    assert db.query(Tag).filter(Tag.id == "tag_zs").first() is not None
    assert db.query(DocumentTag).filter(DocumentTag.tag_id == "tag_zs").count() == links_before


def test_non_creator_cannot_delete_tag_with_relations_data_unchanged(ctx):
    client, db = ctx
    link_count_before = db.query(DocumentTag).filter(DocumentTag.tag_id == "tag_zs").count()
    tag_count_before = db.query(Tag).count()
    assert db.query(Tag).filter(Tag.id == "tag_zs").first() is not None
    assert link_count_before > 0

    # 李四（非创建者）尝试删除张三创建的、有关联的标签 → 拒绝
    resp = client.delete("/api/v1/tags/tag_zs", params={"user_id": "u_lisi"})
    assert resp.status_code == 404

    # 数据保持不变：标签仍在、标签总数不变、关联数量不变
    assert db.query(Tag).filter(Tag.id == "tag_zs").first() is not None
    assert db.query(Tag).count() == tag_count_before
    assert db.query(DocumentTag).filter(DocumentTag.tag_id == "tag_zs").count() == link_count_before


def test_delete_tag_after_relations_removed(ctx):
    client, db = ctx
    # 由各文档所有者解除自己的关联
    for doc_id, uid in [
        ("zs_public", "u_zhangsan"), ("zs_private", "u_zhangsan"),
        ("zs_deleted", "u_zhangsan"), ("ls_public", "u_lisi"),
        ("ls_private", "u_lisi"), ("ls_deleted", "u_lisi"),
    ]:
        db.query(DocumentTag).filter(
            DocumentTag.document_id == doc_id,
            DocumentTag.tag_id == "tag_zs",
        ).delete(synchronize_session=False)
    db.commit()
    resp = client.delete("/api/v1/tags/tag_zs", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 200
    assert db.query(Tag).filter(Tag.id == "tag_zs").first() is None


def test_legacy_tag_without_creator_cannot_be_deleted_by_anyone(ctx):
    client, db = ctx
    # 历史标签 creator_id 为 NULL，无人可冒名删除
    resp = client.delete("/api/v1/tags/tag_legacy", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 404
    assert db.query(Tag).filter(Tag.id == "tag_legacy").first() is not None


# ---------- 关联：文档管理权限校验 ----------

def test_add_tag_requires_document_ownership(ctx):
    client, db = ctx
    # 张三尝试给李四的文档加标签 → 拒绝
    resp = client.post(
        "/api/v1/documents/ls_public/tags/tag_ls",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.status_code == 404
    assert db.query(DocumentTag).filter(
        DocumentTag.document_id == "ls_public",
        DocumentTag.tag_id == "tag_ls",
    ).first() is None


def test_remove_tag_requires_document_ownership(ctx):
    client, db = ctx
    # 张三尝试移除李四文档上的标签 → 拒绝，关联仍在
    resp = client.delete(
        "/api/v1/documents/ls_public/tags/tag_zs",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.status_code == 404
    assert db.query(DocumentTag).filter(
        DocumentTag.document_id == "ls_public",
        DocumentTag.tag_id == "tag_zs",
    ).first() is not None


def test_owner_can_add_and_remove_tag_on_own_doc(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/documents/ls_private/tags/tag_ls",
        params={"user_id": "u_lisi"},
    )
    assert resp.status_code == 200
    resp = client.delete(
        "/api/v1/documents/ls_private/tags/tag_ls",
        params={"user_id": "u_lisi"},
    )
    assert resp.status_code == 200


# ---------- 标签关联文档查询：可见范围 + 软删除 ----------

def test_tag_documents_filtered_by_viewer_scope(ctx):
    client, _ = ctx
    # 张三视角：自己的文档（含私有）+ 他人公开文档；排除他人私有
    zhang = _ids(client.get("/api/v1/tags/Python/documents", params={"user_id": "u_zhangsan"}))
    assert "zs_public" in zhang and "zs_private" in zhang
    assert "ls_public" in zhang
    assert "ls_private" not in zhang

    # 李四视角：自己的文档（含私有）+ 他人公开文档
    lisi = _ids(client.get("/api/v1/tags/Python/documents", params={"user_id": "u_lisi"}))
    assert "ls_public" in lisi and "ls_private" in lisi
    assert "zs_public" in lisi
    assert "zs_private" not in lisi


def test_tag_documents_exclude_soft_deleted(ctx):
    client, _ = ctx
    zhang = _ids(client.get("/api/v1/tags/Python/documents", params={"user_id": "u_zhangsan"}))
    lisi = _ids(client.get("/api/v1/tags/Python/documents", params={"user_id": "u_lisi"}))
    # 已删文档无论所有者都不出现
    assert "zs_deleted" not in zhang and "ls_deleted" not in lisi


# ---------- 置顶：全局共享 ----------

def test_pin_tag_is_global_state(ctx):
    client, db = ctx
    # tag_zs 初始未置顶；任意用户切换后所有用户看到一致
    before = client.get("/api/v1/tags").json()
    assert next(t for t in before if t["id"] == "tag_zs")["pinned"] is False

    resp = client.post("/api/v1/tags/tag_zs/pin", params={"user_id": "u_lisi"})
    assert resp.status_code == 200
    assert resp.json()["pinned"] is True

    zhang = client.get("/api/v1/tags").json()
    assert next(t for t in zhang if t["id"] == "tag_zs")["pinned"] is True

    # 非创建者也可置顶（全局共享状态，不限制创建者）
    resp = client.post("/api/v1/tags/tag_zs/pin", params={"user_id": "u_zhangsan"})
    assert resp.json()["pinned"] is False


# ---------- 迁移脚本兼容 ----------

def test_migration_is_idempotent_and_adds_creator_column(tmp_path):
    """迁移脚本幂等，且历史数据 creator_id 为 NULL。"""
    import os
    from migrations.migrate_tag_creator import migrate
    import migrations.migrate_tag_creator as mig

    db_path = tmp_path / "mig.db"
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE tags (id VARCHAR PRIMARY KEY, name VARCHAR, pinned BOOLEAN)"
        ))
        conn.execute(text("INSERT INTO tags VALUES ('t1', '旧标签', 0)"))

    orig_engine = mig.engine
    mig.engine = eng
    try:
        migrate()  # 第一次
        migrate()  # 幂等复跑
    finally:
        mig.engine = orig_engine

    with eng.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(tags)")).fetchall()]
        assert "creator_id" in cols
        row = conn.execute(text("SELECT creator_id FROM tags WHERE id='t1'")).fetchone()
        assert row[0] is None        # 历史数据 creator_id 为 NULL
        cnt = conn.execute(text("SELECT count(*) FROM tags")).fetchone()[0]
        assert cnt == 1              # 数据行数不变
    eng.dispose()
