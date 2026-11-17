"""Issue #47：文档归属、元信息修改与软删除生命周期的接口层测试。

覆盖验收标准：
- 元信息接口仅允许约定字段、不触发 reindex（chunk 数量/内容不变）；
- 所有者/非所有者的修改、公开、删除、恢复、彻底删除；
- 软删除后各入口（列表/未分类/公开广场/作者主页/文件夹/筛选/收藏/检索/正文）过滤；
- 恢复、彻底删除（关联数据与文件清理）及文件清理异常可追踪。

使用独立内存 SQLite + dependency_overrides，不触碰真实数据库。
"""

import json
import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base, get_db
from modules.ingest.domain.models import User, Document, Chunk, FavoriteDocument
from modules.manage.domain.models import (
    Folder, DocumentFolder, Tag, DocumentTag,
)
from api.router import api_router


def _make_doc(doc_id, owner, title, public=False, deleted=False, source_url=None):
    return Document(
        id=doc_id,
        title=title,
        source_type="text",
        source_url=source_url,
        is_public=public,
        owner_id=owner,
        is_deleted=deleted,
    )


@pytest.fixture
def ctx(tmp_path):
    """构建测试用内存库 + 客户端，返回 (client, db, sessions)。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()

    db.add_all([
        User(id="u_zhangsan", nickname="张三"),
        User(id="u_lisi", nickname="李四"),
    ])
    db.add_all([
        _make_doc("doc_active", "u_zhangsan", "活跃公开文档", public=True),
        _make_doc("doc_private_active", "u_zhangsan", "活跃私有文档"),
        _make_doc("doc_deleted", "u_zhangsan", "已删除公开文档", public=True, deleted=True),
        _make_doc("doc_lisi", "u_lisi", "李四的文档", public=True),
    ])
    # 活跃文档 2 个 chunk，已删除文档 1 个 chunk
    db.add_all([
        Chunk(id="c1", document_id="doc_active", content="知识库检索", embedding=None, chunk_index=0),
        Chunk(id="c2", document_id="doc_active", content="标题内容", embedding=None, chunk_index=1),
        Chunk(id="c3", document_id="doc_deleted", content="已删除的知识库内容", embedding=None, chunk_index=0),
    ])
    db.add_all([
        Folder(id="folder1", name="我的文件夹", owner_id="u_zhangsan", is_public=True),
        Tag(id="tag1", name="标签A", pinned=False),
    ])
    db.add_all([
        DocumentFolder(document_id="doc_active", folder_id="folder1"),
        DocumentFolder(document_id="doc_deleted", folder_id="folder1"),
        DocumentTag(document_id="doc_active", tag_id="tag1"),
        DocumentTag(document_id="doc_deleted", tag_id="tag1"),
        FavoriteDocument(user_id="u_zhangsan", document_id="doc_active"),
        FavoriteDocument(user_id="u_zhangsan", document_id="doc_deleted"),
    ])
    db.commit()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c, db

    db.close()
    engine.dispose()


# ---------- 元信息修改规则 A ----------

def test_update_meta_allows_title_and_keeps_chunks(ctx):
    client, db = ctx
    before = db.query(Chunk).filter(Chunk.document_id == "doc_active").count()

    resp = client.put(
        "/api/v1/documents/doc_active/meta",
        params={"user_id": "u_zhangsan"},
        json={"title": "新标题"},
    )
    assert resp.status_code == 200
    assert db.query(Document).filter(Document.id == "doc_active").first().title == "新标题"

    # 未触发 reindex：chunk 数量与内容不变
    after = db.query(Chunk).filter(Chunk.document_id == "doc_active").count()
    assert after == before == 2


def test_update_meta_rejects_content(ctx):
    """规则 A：不允许通过元信息接口修改原始内容。"""
    client, db = ctx
    resp = client.put(
        "/api/v1/documents/doc_active/meta",
        params={"user_id": "u_zhangsan"},
        json={"content": "试图改正文"},
    )
    assert resp.status_code == 400
    assert "不支持修改的字段" in resp.json()["detail"]


def test_non_owner_cannot_update_meta(ctx):
    client, db = ctx
    resp = client.put(
        "/api/v1/documents/doc_active/meta",
        params={"user_id": "u_lisi"},
        json={"title": "他人篡改"},
    )
    assert resp.status_code == 404
    assert db.query(Document).filter(Document.id == "doc_active").first().title == "活跃公开文档"


# ---------- 公开状态与删除的所有权校验 ----------

def test_non_owner_cannot_toggle_visibility(ctx):
    client, db = ctx
    before = db.query(Document).filter(Document.id == "doc_active").first().is_public
    resp = client.post(
        "/api/v1/documents/doc_active/toggle-visibility",
        params={"user_id": "u_lisi"},
    )
    assert resp.status_code == 200
    assert resp.json().get("error") == "not found"
    assert db.query(Document).filter(Document.id == "doc_active").first().is_public == before


def test_owner_can_soft_delete_and_non_owner_cannot(ctx):
    client, db = ctx
    # 非所有者删除失败
    resp = client.delete("/api/v1/documents/doc_active", params={"user_id": "u_lisi"})
    assert resp.json().get("error") == "文档不存在或无权操作"
    assert db.query(Document).filter(Document.id == "doc_active").first().is_deleted is False

    # 所有者删除成功 -> 软删除，chunk 仍在
    resp = client.delete("/api/v1/documents/doc_active", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 200
    assert resp.json()["is_deleted"] is True
    doc = db.query(Document).filter(Document.id == "doc_active").first()
    assert doc.is_deleted is True
    assert doc.deleted_at is not None
    assert db.query(Chunk).filter(Chunk.document_id == "doc_active").count() == 2


def test_soft_deleted_excluded_from_all_entries(ctx):
    """软删除后各入口均排除已删除文档。"""
    client, db = ctx
    # 前置：doc_deleted 已是软删除；doc_active 未删除
    assert db.query(Document).filter(Document.id == "doc_deleted").first().is_deleted is True

    def titles(resp):
        return {d["title"] for d in resp.json()}

    # 个人文档列表
    r = client.get("/api/v1/documents/all", params={"user_id": "u_zhangsan"})
    assert "已删除公开文档" not in titles(r)

    # 未分类列表（doc 已加入文件夹，这里主要验证不报错且无已删除项）
    r = client.get("/api/v1/documents/uncategorized", params={"user_id": "u_zhangsan"})
    assert "已删除公开文档" not in titles(r)

    # 文档筛选
    r = client.get("/api/v1/documents/filter", params={"user_id": "u_zhangsan"})
    assert "已删除公开文档" not in titles(r)

    # 公开广场
    r = client.get("/api/v1/square", params={"user_id": "u_zhangsan"})
    assert "已删除公开文档" not in titles(r)

    # 作者主页
    r = client.get("/api/v1/users/u_zhangsan/docs")
    assert "已删除公开文档" not in titles(r)

    # 文件夹内容
    r = client.get("/api/v1/folders/folder1/documents", params={"user_id": "u_zhangsan"})
    assert "已删除公开文档" not in titles(r)

    # 公开文件夹文档
    r = client.get("/api/v1/square/folders/folder1/docs")
    assert "已删除公开文档" not in titles(r)

    # 标签下文档
    r = client.get("/api/v1/tags/标签A/documents", params={"user_id": "u_zhangsan"})
    assert "已删除公开文档" not in titles(r)

    # 收藏列表
    r = client.get("/api/v1/favorites", params={"user_id": "u_zhangsan"})
    fav_titles = {d["title"] for d in r.json()["documents"]}
    assert "已删除公开文档" not in fav_titles

    # 正文读取：已删除文档返回 404
    r = client.get("/api/v1/documents/doc_deleted/content", params={"user_id": "u_zhangsan"})
    assert r.status_code == 404


def test_soft_deleted_chunk_excluded_from_keyword_search(ctx):
    """检索排除已删除文档的 chunk（规则 C）。"""
    import asyncio
    from modules.retrieve.repository import chunk_repo

    engine_db = None
    # ctx 内的 db 是 Session，直接传给 repo
    client, db = ctx
    results = chunk_repo.search_by_keywords(db, ["知识库"], top_k=10)
    ids = {c.id for c in results}
    # c3 属于已删除文档，必须被排除；c1 属于活跃文档
    assert "c3" not in ids
    assert "c1" in ids


# ---------- 恢复与彻底删除 ----------

def test_restore_document_owner_only(ctx):
    client, db = ctx
    # 非所有者恢复失败
    resp = client.post("/api/v1/documents/doc_deleted/restore", params={"user_id": "u_lisi"})
    assert resp.json().get("error") == "文档不存在或无权操作"

    # 所有者恢复成功
    resp = client.post("/api/v1/documents/doc_deleted/restore", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 200
    assert resp.json()["is_deleted"] is False
    doc = db.query(Document).filter(Document.id == "doc_deleted").first()
    assert doc.is_deleted is False
    assert doc.deleted_at is None


def test_permanent_delete_cleans_relations_owner_only(ctx):
    client, db = ctx
    # 非所有者彻底删除失败
    resp = client.delete("/api/v1/documents/doc_deleted/permanent", params={"user_id": "u_lisi"})
    assert resp.json().get("error") == "文档不存在或无权操作"

    # 所有者彻底删除成功
    resp = client.delete("/api/v1/documents/doc_deleted/permanent", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    assert db.query(Document).filter(Document.id == "doc_deleted").first() is None
    assert db.query(Chunk).filter(Chunk.document_id == "doc_deleted").count() == 0
    assert db.query(DocumentFolder).filter(DocumentFolder.document_id == "doc_deleted").count() == 0
    assert db.query(DocumentTag).filter(DocumentTag.document_id == "doc_deleted").count() == 0
    assert db.query(FavoriteDocument).filter(FavoriteDocument.document_id == "doc_deleted").count() == 0


def test_permanent_delete_requires_soft_deleted_first(ctx):
    """彻底删除只针对已软删除文档，活跃文档不可直接彻底删除。"""
    client, db = ctx
    resp = client.delete("/api/v1/documents/doc_active/permanent", params={"user_id": "u_zhangsan"})
    assert resp.json().get("error") == "文档不存在或无权操作"
    assert db.query(Document).filter(Document.id == "doc_active").first() is not None


def test_permanent_delete_file_cleanup_failure_is_tracked(ctx, tmp_path, monkeypatch):
    """文件清理失败应返回可追踪结果，不回滚数据库；上传目录与清单隔离到临时目录。"""
    client, db = ctx

    # Issue #54：删除生命周期已迁入 document_service，monkeypatch 目标同步更新。
    import modules.manage.service.document_service as fs
    # 副作用隔离：chdir 到 tmp_path，令 uploads 相对路径指向临时目录；
    # 清单路径也显式指向同一临时目录，绝不污染真实 uploads/。
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    isolated_manifest = upload_dir / ".orphan_cleanup.json"
    monkeypatch.setattr(fs, "ORPHAN_CLEANUP_FILE", str(isolated_manifest))
    monkeypatch.chdir(tmp_path)

    # 给已删除文档一个指向不存在文件的 source_url，并让 os.remove 抛错
    doc = db.query(Document).filter(Document.id == "doc_deleted").first()
    doc.source_url = "/uploads/missing_file.txt"
    db.commit()

    monkeypatch.setattr(fs.os.path, "exists", lambda p: True)
    monkeypatch.setattr(fs.os, "remove", lambda p: (_ for _ in ()).throw(OSError("磁盘错误")))

    resp = client.delete("/api/v1/documents/doc_deleted/permanent", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert str(resp.json()["file_cleanup"]).startswith("failed:")
    # 数据库已彻底删除，不因文件失败而回滚
    assert db.query(Document).filter(Document.id == "doc_deleted").first() is None
    # 新增断言（增强而非弱化）：清单确实落在隔离目录且登记了失败文件
    assert isolated_manifest.exists()
    entries = json.loads(isolated_manifest.read_text(encoding="utf-8"))
    assert any(
        e["doc_id"] == "doc_deleted" and e["path"] == "missing_file.txt"
        for e in entries
    )
