"""Issue #49：文档与文件夹收藏的可见性、归属与列表过滤接口层测试。

覆盖验收标准：
- 文档/文件夹收藏统一使用当前用户上下文；
- 私有文档仅所有者可收藏，公开文档可按公开规则收藏；
- 私有文件夹不能被非所有者收藏；
- 重复点击按 toggle 语义正确切换；
- 收藏列表只返回当前用户可访问且未软删除的资源；
- 取消收藏只删关系，不删资源；
- 跨用户、私有/公开资源、重复点击、软删除、取消收藏全覆盖。

使用独立内存 SQLite + dependency_overrides，不触碰真实数据库。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base, get_db
from modules.ingest.domain.models import User, Document, FavoriteDocument
from modules.manage.domain.models import Folder, FavoriteFolder, DocumentFolder
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


def _folder(folder_id, owner, name, public=False):
    return Folder(id=folder_id, name=name, owner_id=owner, is_public=public)


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
        _doc("doc_own_public", "u_zhangsan", "张三公开文档", public=True),
        _doc("doc_own_private", "u_zhangsan", "张三私有文档"),
        _doc("doc_own_deleted", "u_zhangsan", "张三已删文档", public=True, deleted=True),
        _doc("doc_lisi_public", "u_lisi", "李四公开文档", public=True),
        _doc("doc_lisi_private", "u_lisi", "李四私有文档"),
        _doc("doc_own_public_extra", "u_zhangsan", "张三公开文档2", public=True),
        _doc("doc_lisi_public_extra", "u_lisi", "李四公开文档2", public=True),
    ])
    db.add_all([
        _folder("f_own_public", "u_zhangsan", "张三公开文件夹", public=True),
        _folder("f_own_private", "u_zhangsan", "张三私有文件夹"),
        _folder("f_lisi_public", "u_lisi", "李四公开文件夹", public=True),
        _folder("f_lisi_private", "u_lisi", "李四私有文件夹"),
        _folder("f_own_public_extra", "u_zhangsan", "张三公开文件夹2", public=True),
        _folder("f_lisi_public_extra", "u_lisi", "李四公开文件夹2", public=True),
    ])
    # 预置跨用户收藏，便于验证列表隔离与失效隐藏
    db.add_all([
        FavoriteDocument(user_id="u_zhangsan", document_id="doc_lisi_public"),
        FavoriteDocument(user_id="u_lisi", document_id="doc_own_public"),
        FavoriteFolder(user_id="u_lisi", folder_id="f_own_public"),
        FavoriteFolder(user_id="u_zhangsan", folder_id="f_lisi_public"),
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


def _fav_doc_ids(db, user_id):
    return {
        f.document_id
        for f in db.query(FavoriteDocument).filter(
            FavoriteDocument.user_id == user_id
        ).all()
    }


def _fav_folder_ids(db, user_id):
    return {
        f.folder_id
        for f in db.query(FavoriteFolder).filter(
            FavoriteFolder.user_id == user_id
        ).all()
    }


def _fav_titles(resp, key):
    return {item["title"] if key == "documents" else item["name"] for item in resp.json()[key]}


# ---------- 文档收藏：可见性 ----------

def test_favorite_own_private_document_allowed(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/doc/doc_own_private",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json()["status"] == "added"
    assert "doc_own_private" in _fav_doc_ids(db, "u_zhangsan")


def test_favorite_public_document_allowed(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/doc/doc_lisi_public_extra",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json()["status"] == "added"
    assert "doc_lisi_public_extra" in _fav_doc_ids(db, "u_zhangsan")


def test_favorite_others_private_document_rejected(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/doc/doc_lisi_private",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文档不存在或无权收藏"
    assert "doc_lisi_private" not in _fav_doc_ids(db, "u_zhangsan")


def test_favorite_own_private_document_by_other_user_rejected(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/doc/doc_own_private",
        params={"user_id": "u_lisi"},
    )
    assert resp.json().get("error") == "文档不存在或无权收藏"
    assert "doc_own_private" not in _fav_doc_ids(db, "u_lisi")


def test_favorite_soft_deleted_document_rejected(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/doc/doc_own_deleted",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文档不存在"
    assert "doc_own_deleted" not in _fav_doc_ids(db, "u_zhangsan")


def test_favorite_nonexistent_document_rejected(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/doc/not_exists",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文档不存在"
    assert "not_exists" not in _fav_doc_ids(db, "u_zhangsan")


# ---------- 文件夹收藏：可见性 ----------

def test_favorite_own_private_folder_allowed(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/folder/f_own_private",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json()["status"] == "added"
    assert "f_own_private" in _fav_folder_ids(db, "u_zhangsan")


def test_favorite_public_folder_allowed(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/folder/f_lisi_public_extra",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json()["status"] == "added"
    assert "f_lisi_public_extra" in _fav_folder_ids(db, "u_zhangsan")


def test_favorite_others_private_folder_rejected(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/folder/f_lisi_private",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文件夹不存在或无权收藏"
    assert "f_lisi_private" not in _fav_folder_ids(db, "u_zhangsan")


def test_favorite_nonexistent_folder_rejected(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/folder/not_exists",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文件夹不存在"
    assert "not_exists" not in _fav_folder_ids(db, "u_zhangsan")


# ---------- 重复点击与取消收藏 ----------

def test_repeated_document_toggle_switches(ctx):
    client, db = ctx
    url = "/api/v1/favorites/doc/doc_lisi_public_extra"
    assert client.post(url, params={"user_id": "u_zhangsan"}).json()["status"] == "added"
    assert client.post(url, params={"user_id": "u_zhangsan"}).json()["status"] == "removed"
    assert client.post(url, params={"user_id": "u_zhangsan"}).json()["status"] == "added"
    assert "doc_lisi_public_extra" in _fav_doc_ids(db, "u_zhangsan")


def test_repeated_folder_toggle_switches(ctx):
    client, db = ctx
    url = "/api/v1/favorites/folder/f_lisi_public_extra"
    assert client.post(url, params={"user_id": "u_zhangsan"}).json()["status"] == "added"
    assert client.post(url, params={"user_id": "u_zhangsan"}).json()["status"] == "removed"
    assert client.post(url, params={"user_id": "u_zhangsan"}).json()["status"] == "added"
    assert "f_lisi_public_extra" in _fav_folder_ids(db, "u_zhangsan")


def test_cancel_favorite_does_not_delete_resource(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/doc/doc_own_public",
        params={"user_id": "u_lisi"},
    )
    assert resp.json()["status"] == "removed"
    # 只删收藏关系，不删被收藏的文档
    assert db.query(Document).filter(Document.id == "doc_own_public").first() is not None
    assert "doc_own_public" not in _fav_doc_ids(db, "u_lisi")


def test_cancel_favorite_allowed_when_resource_inaccessible(ctx):
    """资源变为不可访问后仍允许取消收藏，便于清理无效关系。"""
    client, db = ctx
    doc = db.query(Document).filter(Document.id == "doc_own_public").first()
    doc.is_public = False
    db.commit()

    resp = client.post(
        "/api/v1/favorites/doc/doc_own_public",
        params={"user_id": "u_lisi"},
    )
    assert resp.json()["status"] == "removed"
    assert "doc_own_public" not in _fav_doc_ids(db, "u_lisi")


# ---------- 收藏列表：隔离与失效隐藏 ----------

def test_favorites_list_is_scoped_to_current_user(ctx):
    client, db = ctx
    zhangsan = client.get("/api/v1/favorites", params={"user_id": "u_zhangsan"}).json()
    lisi = client.get("/api/v1/favorites", params={"user_id": "u_lisi"}).json()

    assert {d["id"] for d in zhangsan["documents"]} == {"doc_lisi_public"}
    assert {d["id"] for d in lisi["documents"]} == {"doc_own_public"}
    assert {f["id"] for f in zhangsan["folders"]} == {"f_lisi_public"}
    assert {f["id"] for f in lisi["folders"]} == {"f_own_public"}


def test_favorites_list_hides_soft_deleted_document(ctx):
    client, db = ctx
    added = client.post(
        "/api/v1/favorites/doc/doc_own_public_extra",
        params={"user_id": "u_zhangsan"},
    )
    assert added.json()["status"] == "added"
    assert "张三公开文档2" in _fav_titles(
        client.get("/api/v1/favorites", params={"user_id": "u_zhangsan"}), "documents"
    )

    doc = db.query(Document).filter(Document.id == "doc_own_public_extra").first()
    doc.is_deleted = True
    db.commit()

    titles = _fav_titles(
        client.get("/api/v1/favorites", params={"user_id": "u_zhangsan"}), "documents"
    )
    assert "张三公开文档2" not in titles


def test_favorites_list_hides_document_that_became_private(ctx):
    client, db = ctx
    assert "张三公开文档" in _fav_titles(
        client.get("/api/v1/favorites", params={"user_id": "u_lisi"}), "documents"
    )

    doc = db.query(Document).filter(Document.id == "doc_own_public").first()
    doc.is_public = False
    db.commit()

    assert "张三公开文档" not in _fav_titles(
        client.get("/api/v1/favorites", params={"user_id": "u_lisi"}), "documents"
    )


def test_favorites_list_hides_folder_that_became_private(ctx):
    client, db = ctx
    assert "张三公开文件夹" in _fav_titles(
        client.get("/api/v1/favorites", params={"user_id": "u_lisi"}), "folders"
    )

    folder = db.query(Folder).filter(Folder.id == "f_own_public").first()
    folder.is_public = False
    db.commit()

    assert "张三公开文件夹" not in _fav_titles(
        client.get("/api/v1/favorites", params={"user_id": "u_lisi"}), "folders"
    )


def test_favorites_list_hides_deleted_folder(ctx):
    client, db = ctx
    db.delete(db.query(Folder).filter(Folder.id == "f_own_public").first())
    db.query(DocumentFolder).filter(
        DocumentFolder.folder_id == "f_own_public"
    ).delete()
    db.commit()

    assert "张三公开文件夹" not in _fav_titles(
        client.get("/api/v1/favorites", params={"user_id": "u_lisi"}), "folders"
    )
