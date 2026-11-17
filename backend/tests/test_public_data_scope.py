"""Issue #50：公开广场、公开文件夹、作者主页与正文详情的数据范围一致性测试。

覆盖验收标准：
- 广场只返回可公开浏览且未软删除的文档；
- 公开文件夹列表只返回公开文件夹；
- 公开文件夹详情二次校验文件夹公开状态，只展示公开且未删除文档；
- 作者主页只展示目标作者公开且未软删除文档，路径参数是目标作者；
- 私有文档不能通过更换 doc_id（正文 URL）/folder_id/author_id 绕过公开规则；
- 收藏状态只按当前浏览者自己的收藏关系计算；
- 取消公开、软删除后公开入口同步移除。

使用独立内存 SQLite + dependency_overrides，不触碰真实数据库与 uploads。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base, get_db
from modules.ingest.domain.models import User, Document, Chunk, FavoriteDocument
from modules.manage.domain.models import Folder, DocumentFolder, FavoriteFolder
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
        User(id="u_zhangsan", nickname="张三", avatar="Z"),
        User(id="u_lisi", nickname="李四", avatar="L"),
        User(id="u_wangwu", nickname="王五", avatar="W"),
    ])
    db.add_all([
        _doc("zs_public", "u_zhangsan", "张三公开", public=True),
        _doc("zs_private", "u_zhangsan", "张三私有"),
        _doc("zs_deleted", "u_zhangsan", "张三已删公开", public=True, deleted=True),
        _doc("ls_public", "u_lisi", "李四公开", public=True),
        _doc("ls_private", "u_lisi", "李四私有"),
        _doc("ls_deleted", "u_lisi", "李四已删公开", public=True, deleted=True),
        # 未归入公开文件夹的公开文档：广场列表展示（既有设计排除公开文件夹内文档）
        _doc("zs_square", "u_zhangsan", "张三广场文档", public=True),
        _doc("ls_square", "u_lisi", "李四广场文档", public=True),
    ])
    db.add_all([
        Chunk(id="c_zs_public", document_id="zs_public", content="张三公开正文", chunk_index=0),
        Chunk(id="c_zs_private", document_id="zs_private", content="张三私有正文", chunk_index=0),
        Chunk(id="c_ls_public", document_id="ls_public", content="李四公开正文", chunk_index=0),
        Chunk(id="c_ls_private", document_id="ls_private", content="李四私有正文", chunk_index=0),
    ])
    db.add_all([
        _folder("f_zs_public", "u_zhangsan", "张三公开夹", public=True),
        _folder("f_zs_private", "u_zhangsan", "张三私有夹"),
        _folder("f_ls_public", "u_lisi", "李四公开夹", public=True),
        _folder("f_ls_private", "u_lisi", "李四私有夹"),
    ])
    # 公开文件夹内混入私有/已删文档，验证详情二次过滤
    db.add_all([
        DocumentFolder(document_id="zs_public", folder_id="f_zs_public"),
        DocumentFolder(document_id="zs_private", folder_id="f_zs_public"),
        DocumentFolder(document_id="zs_deleted", folder_id="f_zs_public"),
        DocumentFolder(document_id="ls_public", folder_id="f_ls_public"),
        DocumentFolder(document_id="ls_private", folder_id="f_ls_public"),
        DocumentFolder(document_id="ls_deleted", folder_id="f_ls_public"),
        # 私有文件夹内也有公开文档，验证私有文件夹直连不泄露
        DocumentFolder(document_id="ls_public", folder_id="f_ls_private"),
    ])
    # 张三收藏了李四广场文档与李四公开文件夹；李四收藏了张三广场文档
    db.add_all([
        FavoriteDocument(user_id="u_zhangsan", document_id="ls_square"),
        FavoriteFolder(user_id="u_zhangsan", folder_id="f_ls_public"),
        FavoriteDocument(user_id="u_lisi", document_id="zs_square"),
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


# ---------- 广场 ----------

def test_square_returns_only_public_and_not_deleted(ctx):
    client, _ = ctx
    resp = client.get("/api/v1/square", params={"user_id": "u_wangwu"})
    assert resp.status_code == 200
    ids = _ids(resp)
    # 广场展示未归入公开文件夹的公开文档
    assert "zs_square" in ids and "ls_square" in ids
    assert "zs_private" not in ids and "ls_private" not in ids
    assert "zs_deleted" not in ids and "ls_deleted" not in ids


def test_square_keyword_search_keeps_public_scope(ctx):
    client, _ = ctx
    resp = client.get("/api/v1/square", params={"user_id": "u_wangwu", "keyword": "李四"})
    assert resp.status_code == 200
    ids = _ids(resp)
    assert "ls_square" in ids
    assert "ls_private" not in ids and "ls_deleted" not in ids


# ---------- 公开文件夹列表 ----------

def test_square_folders_only_public(ctx):
    client, _ = ctx
    resp = client.get("/api/v1/square/folders", params={"user_id": "u_wangwu"})
    assert resp.status_code == 200
    ids = _ids(resp)
    assert ids == {"f_zs_public", "f_ls_public"}
    assert "f_zs_private" not in ids and "f_ls_private" not in ids


# ---------- 公开文件夹详情 ----------

def test_public_folder_detail_rechecks_public_and_doc_scope(ctx):
    client, _ = ctx
    resp = client.get("/api/v1/square/folders/f_ls_public/docs")
    assert resp.status_code == 200
    ids = _ids(resp)
    # 仅公开且未删除文档；私有/已删文档即便在公开文件夹内也不展示
    assert ids == {"ls_public"}
    assert "ls_private" not in ids and "ls_deleted" not in ids


def test_private_folder_id_cannot_bypass(ctx):
    client, _ = ctx
    # 私有文件夹即便内含公开文档，换 folder_id 也不得读取
    resp = client.get("/api/v1/square/folders/f_ls_private/docs")
    assert resp.status_code == 200
    assert resp.json() == []
    # 不存在的 folder_id 同样返回空，不泄露
    resp = client.get("/api/v1/square/folders/f_not_exist/docs")
    assert resp.json() == []


# ---------- 作者主页 ----------

def test_author_profile_only_target_author_public_not_deleted(ctx):
    client, _ = ctx
    # 目标作者路径参数是 author_id，不是当前操作者
    resp = client.get("/api/v1/users/u_lisi/docs")
    assert resp.status_code == 200
    ids = _ids(resp)
    # 作者主页展示目标作者的全部公开未删文档（含归入公开文件夹的）
    assert ids == {"ls_public", "ls_square"}
    assert "ls_private" not in ids and "ls_deleted" not in ids
    assert "zs_public" not in ids  # 不混入他人文档


def test_author_profile_unknown_author_is_empty(ctx):
    client, _ = ctx
    resp = client.get("/api/v1/users/u_not_exist/docs")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------- 正文详情：更换 URL 绕过防护 ----------

def test_content_owner_can_read_own_private(ctx):
    client, _ = ctx
    resp = client.get(
        "/api/v1/documents/zs_private/content",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "张三私有正文"


def test_content_public_doc_readable_by_any_browser(ctx):
    client, _ = ctx
    resp = client.get(
        "/api/v1/documents/ls_public/content",
        params={"user_id": "u_wangwu"},
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "李四公开正文"


def test_content_other_private_doc_bypass_is_404(ctx):
    client, _ = ctx
    # 换 doc_id 读取他人私有正文必须被拒绝，且不泄露存在性
    resp = client.get(
        "/api/v1/documents/ls_private/content",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.status_code == 404


def test_content_deleted_doc_is_404_even_for_owner(ctx):
    client, _ = ctx
    resp = client.get(
        "/api/v1/documents/zs_deleted/content",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.status_code == 404


# ---------- 收藏状态按当前浏览者 ----------

def test_square_favorite_flag_is_per_browser(ctx):
    client, _ = ctx
    zhang = client.get("/api/v1/square", params={"user_id": "u_zhangsan"}).json()
    wang = client.get("/api/v1/square", params={"user_id": "u_wangwu"}).json()
    zhang_map = {d["id"]: d["is_favorited"] for d in zhang}
    wang_map = {d["id"]: d["is_favorited"] for d in wang}
    # 张三收藏了 ls_square，王五没有
    assert zhang_map["ls_square"] is True
    assert wang_map["ls_square"] is False
    # 李四收藏了 zs_square，张三没有
    assert zhang_map["zs_square"] is False
    assert wang_map["zs_square"] is False


def test_square_folders_favorite_flag_is_per_browser(ctx):
    client, _ = ctx
    zhang = client.get("/api/v1/square/folders", params={"user_id": "u_zhangsan"}).json()
    wang = client.get("/api/v1/square/folders", params={"user_id": "u_wangwu"}).json()
    zhang_map = {f["id"]: f["is_favorited"] for f in zhang}
    wang_map = {f["id"]: f["is_favorited"] for f in wang}
    assert zhang_map["f_ls_public"] is True
    assert wang_map["f_ls_public"] is False


# ---------- 取消公开 / 软删除后公开入口同步移除 ----------

def test_cancel_public_removes_from_all_public_entries(ctx):
    client, db = ctx
    # 取消 zs_square（广场文档）的公开状态，验证广场/作者主页/正文同步移除
    resp = client.post(
        "/api/v1/documents/zs_square/toggle-visibility",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_public"] is False

    assert "zs_square" not in _ids(client.get("/api/v1/square", params={"user_id": "u_wangwu"}))
    assert "zs_square" not in _ids(client.get("/api/v1/users/u_zhangsan/docs"))
    # 正文：他人浏览器不可再读私有化后的文档
    resp = client.get(
        "/api/v1/documents/zs_square/content",
        params={"user_id": "u_wangwu"},
    )
    assert resp.status_code == 404

    # 文件夹内文档取消公开后，也从公开文件夹详情移除
    resp = client.post(
        "/api/v1/documents/zs_public/toggle-visibility",
        params={"user_id": "u_zhangsan"},
    )
    assert resp.json()["is_public"] is False
    assert "zs_public" not in _ids(client.get("/api/v1/square/folders/f_zs_public/docs"))


def test_soft_delete_removes_from_all_public_entries(ctx):
    client, db = ctx
    # 软删除 ls_square（广场文档），验证广场/作者主页/正文同步移除
    doc = db.query(Document).filter(Document.id == "ls_square").first()
    doc.is_deleted = True
    db.commit()

    assert "ls_square" not in _ids(client.get("/api/v1/square", params={"user_id": "u_wangwu"}))
    assert "ls_square" not in _ids(client.get("/api/v1/users/u_lisi/docs"))
    resp = client.get(
        "/api/v1/documents/ls_square/content",
        params={"user_id": "u_wangwu"},
    )
    assert resp.status_code == 404

    # 文件夹内文档软删除后，也从公开文件夹详情移除
    doc = db.query(Document).filter(Document.id == "ls_public").first()
    doc.is_deleted = True
    db.commit()
    assert "ls_public" not in _ids(client.get("/api/v1/square/folders/f_ls_public/docs"))
