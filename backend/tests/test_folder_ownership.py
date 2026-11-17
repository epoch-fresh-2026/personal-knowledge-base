"""Issue #48：文件夹归属、文档关联与公开规则的接口层测试。

覆盖验收标准：
- 创建/列表/重命名/删除文件夹均校验当前用户；
- 添加/移除文档关联同时校验文件夹与文档的归属和状态；
- 私有文件夹不可通过 folder_id 直连读取；
- 删除文件夹只删关联与文件夹，不删文档；
- 公开文件夹列表与详情使用一致的可见性过滤；
- 取消公开不反向修改文档自身 is_public；
- 已软删除文档不出现在文件夹正常/公开内容；
- 收藏不改变文件夹所有者与公开状态。

使用独立内存 SQLite + dependency_overrides，不触碰真实数据库与 uploads。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base, get_db
from modules.ingest.domain.models import User, Document
from modules.manage.domain.models import Folder, DocumentFolder
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
        _doc("doc_lisi_private", "u_lisi", "李四私有文档"),
        _doc("doc_lisi_public", "u_lisi", "李四公开文档", public=True),
    ])
    db.add_all([
        _folder("f_own_public", "u_zhangsan", "张三公开文件夹", public=True),
        _folder("f_own_private", "u_zhangsan", "张三私有文件夹"),
        _folder("f_lisi_private", "u_lisi", "李四私有文件夹"),
        _folder("f_lisi_public", "u_lisi", "李四公开文件夹", public=True),
    ])
    db.add_all([
        DocumentFolder(document_id="doc_own_public", folder_id="f_own_public"),
        DocumentFolder(document_id="doc_own_private", folder_id="f_own_public"),
        DocumentFolder(document_id="doc_own_deleted", folder_id="f_own_public"),
        DocumentFolder(document_id="doc_lisi_public", folder_id="f_lisi_public"),
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


def _titles(resp):
    data = resp.json()
    return {item["title"] for item in data} if isinstance(data, list) else set()


# ---------- 文件夹归属：创建 / 列表 / 重命名 / 删除 ----------

def test_create_and_list_folders_scoped_to_owner(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/folders",
        params={"user_id": "u_zhangsan"},
        json={"name": "新建文件夹"},
    )
    assert resp.status_code == 200
    created = resp.json()
    assert created["owner_id"] == "u_zhangsan"

    mine = client.get("/api/v1/folders", params={"user_id": "u_zhangsan"}).json()
    others = client.get("/api/v1/folders", params={"user_id": "u_lisi"}).json()
    assert {f["id"] for f in mine} == {"f_own_public", "f_own_private", created["id"]}
    assert {f["id"] for f in others} == {"f_lisi_private", "f_lisi_public"}


def test_rename_folder_owner_only(ctx):
    client, db = ctx
    denied = client.put(
        "/api/v1/folders/f_lisi_private/name",
        params={"user_id": "u_zhangsan"},
        json={"new_name": "篡改"},
    )
    assert denied.json().get("error") == "文件夹不存在或无权限"
    assert db.query(Folder).filter(Folder.id == "f_lisi_private").first().name == "李四私有文件夹"

    ok = client.put(
        "/api/v1/folders/f_own_private/name",
        params={"user_id": "u_zhangsan"},
        json={"new_name": "改名成功"},
    )
    assert ok.json()["name"] == "改名成功"


def test_delete_folder_owner_only_and_keeps_documents(ctx):
    client, db = ctx
    denied = client.delete(
        "/api/v1/folders/f_lisi_private",
        params={"user_id": "u_zhangsan"},
    )
    assert denied.json().get("error")
    assert db.query(Folder).filter(Folder.id == "f_lisi_private").first() is not None

    resp = client.delete(
        "/api/v1/folders/f_own_public",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json()["status"] == "success"
    assert db.query(Folder).filter(Folder.id == "f_own_public").first() is None
    assert db.query(DocumentFolder).filter(
        DocumentFolder.folder_id == "f_own_public"
    ).count() == 0
    # 文件夹删除不等于删除文档
    for doc_id in ("doc_own_public", "doc_own_private", "doc_own_deleted"):
        assert db.query(Document).filter(Document.id == doc_id).first() is not None


# ---------- 文档关联：添加 ----------

def test_add_own_document_to_own_folder_is_idempotent(ctx):
    client, db = ctx
    for _ in range(2):
        resp = client.post(
            "/api/v1/folders/f_own_private/documents/doc_own_public",
            params={"user_id": "u_zhangsan"},
        )
        assert resp.json()["status"] == "success"
    assert db.query(DocumentFolder).filter_by(
        document_id="doc_own_public", folder_id="f_own_private"
    ).count() == 1


def test_add_others_private_document_rejected(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/folders/f_own_private/documents/doc_lisi_private",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文档不存在或无权操作"
    assert db.query(DocumentFolder).filter_by(
        document_id="doc_lisi_private", folder_id="f_own_private"
    ).first() is None


def test_add_others_public_document_rejected(ctx):
    """公开不等于可管理：他人公开文档也不得加入自己的文件夹。"""
    client, db = ctx
    resp = client.post(
        "/api/v1/folders/f_own_private/documents/doc_lisi_public",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文档不存在或无权操作"
    assert db.query(DocumentFolder).filter_by(
        document_id="doc_lisi_public", folder_id="f_own_private"
    ).first() is None


def test_add_to_others_folder_rejected(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/folders/f_lisi_public/documents/doc_own_public",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文件夹不存在或无权操作"
    assert db.query(DocumentFolder).filter_by(
        document_id="doc_own_public", folder_id="f_lisi_public"
    ).first() is None


def test_add_soft_deleted_document_rejected(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/folders/f_own_private/documents/doc_own_deleted",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文档不存在或无权操作"
    assert db.query(DocumentFolder).filter_by(
        document_id="doc_own_deleted", folder_id="f_own_private"
    ).first() is None


# ---------- 文档关联：移除 ----------

def test_remove_own_document_removes_only_link(ctx):
    client, db = ctx
    resp = client.delete(
        "/api/v1/folders/f_own_public/documents/doc_own_public",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json()["status"] == "success"
    assert db.query(DocumentFolder).filter_by(
        document_id="doc_own_public", folder_id="f_own_public"
    ).first() is None
    # 只删关联，不删文档
    assert db.query(Document).filter(Document.id == "doc_own_public").first() is not None


def test_cross_user_remove_rejected(ctx):
    client, db = ctx
    resp = client.delete(
        "/api/v1/folders/f_lisi_public/documents/doc_lisi_public",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文件夹不存在或无权操作"
    assert db.query(DocumentFolder).filter_by(
        document_id="doc_lisi_public", folder_id="f_lisi_public"
    ).first() is not None


def test_remove_others_document_from_own_folder_rejected(ctx):
    """历史遗留的跨用户关联：即使文件夹是自己的，也不能代为移除他人文档。"""
    client, db = ctx
    db.add(DocumentFolder(document_id="doc_lisi_public", folder_id="f_own_public"))
    db.commit()

    resp = client.delete(
        "/api/v1/folders/f_own_public/documents/doc_lisi_public",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json().get("error") == "文档不存在或无权操作"
    assert db.query(DocumentFolder).filter_by(
        document_id="doc_lisi_public", folder_id="f_own_public"
    ).first() is not None


# ---------- 文件夹详情：可见性 ----------

def test_private_folder_detail_denied_to_non_owner(ctx):
    client, db = ctx
    resp = client.get(
        "/api/v1/folders/f_own_private/documents",
        params={"user_id": "u_lisi"},
    )
    assert resp.json().get("error") == "文件夹不存在或无权访问"
    assert "张三私有文档" not in str(resp.json())


def test_owner_sees_all_active_docs_in_own_folder(ctx):
    client, db = ctx
    resp = client.get(
        "/api/v1/folders/f_own_public/documents",
        params={"user_id": "u_zhangsan"},
    )
    titles = _titles(resp)
    assert "张三公开文档" in titles
    assert "张三私有文档" in titles  # 所有者可见自身私有文档
    assert "张三已删文档" not in titles  # 软删除一律排除


def test_non_owner_sees_only_public_docs_in_public_folder(ctx):
    client, db = ctx
    resp = client.get(
        "/api/v1/folders/f_own_public/documents",
        params={"user_id": "u_lisi"},
    )
    titles = _titles(resp)
    assert titles == {"张三公开文档"}


# ---------- 公开状态：独立性 ----------

def test_toggle_public_never_changes_document_visibility(ctx):
    client, db = ctx
    before = {
        doc_id: db.query(Document).filter(Document.id == doc_id).first().is_public
        for doc_id in ("doc_own_public", "doc_own_private", "doc_own_deleted")
    }

    on = client.post(
        "/api/v1/folders/f_own_private/toggle-public",
        params={"user_id": "u_zhangsan"},
    )
    assert on.json()["is_public"] is True
    for doc_id, value in before.items():
        assert db.query(Document).filter(Document.id == doc_id).first().is_public == value

    off = client.post(
        "/api/v1/folders/f_own_private/toggle-public",
        params={"user_id": "u_zhangsan"},
    )
    assert off.json()["is_public"] is False
    for doc_id, value in before.items():
        assert db.query(Document).filter(Document.id == doc_id).first().is_public == value


def test_toggle_public_owner_only(ctx):
    client, db = ctx
    resp = client.post(
        "/api/v1/folders/f_own_private/toggle-public",
        params={"user_id": "u_lisi"},
    )
    assert resp.json().get("error") == "文件夹不存在或无权限"
    assert db.query(Folder).filter(Folder.id == "f_own_private").first().is_public is False


def test_public_folder_docs_endpoint_filters_and_rejects_private_folder(ctx):
    client, db = ctx
    public_docs = client.get("/api/v1/square/folders/f_own_public/docs").json()
    assert {d["title"] for d in public_docs} == {"张三公开文档"}
    # 私有文件夹与不存在的文件夹均返回空，不泄露内容
    assert client.get("/api/v1/square/folders/f_own_private/docs").json() == []
    assert client.get("/api/v1/square/folders/not_exists/docs").json() == []


def test_public_folder_list_excludes_private_folder(ctx):
    client, db = ctx
    folders = client.get(
        "/api/v1/square/folders", params={"user_id": "u_lisi"}
    ).json()
    ids = {f["id"] for f in folders}
    assert "f_own_public" in ids
    assert "f_own_private" not in ids


# ---------- 收藏独立性 ----------

def test_favorite_folder_does_not_change_owner_or_visibility(ctx):
    """Issue #49 规则下改用公开文件夹：跨用户收藏不得改变所有者或公开状态。"""
    client, db = ctx
    resp = client.post(
        "/api/v1/favorites/folder/f_own_public",
        params={"user_id": "u_lisi"},
    )
    assert resp.json()["status"] == "added"

    folder = db.query(Folder).filter(Folder.id == "f_own_public").first()
    assert folder.owner_id == "u_zhangsan"
    assert folder.is_public is True

    folders = client.get(
        "/api/v1/square/folders", params={"user_id": "u_lisi"}
    ).json()
    assert "f_own_public" in {f["id"] for f in folders}
