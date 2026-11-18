"""Issue #45：模拟用户上下文的接口层集成测试。

覆盖：默认初始化语义、切换用户后的个人数据隔离、缺失/格式错误/不存在用户，
以及作者主页目标作者与当前操作者不混用。

说明：本测试使用独立内存 SQLite，通过 dependency_overrides 注入，
不触碰真实数据库，也不修改任何数据。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base, get_db
from shared.user_context import validate_user_id_format
from fastapi import HTTPException

# 确保两张模型里定义的表都注册到 Base.metadata
import modules.ingest.domain.models  # noqa: F401
import modules.manage.domain.models  # noqa: F401
from modules.ingest.domain.models import User, Document
from api.router import api_router

from uuid import uuid4


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )
    db = TestingSession()

    db.add_all([
        User(id="u_zhangsan", nickname="张三"),
        User(id="u_lisi", nickname="李四"),
    ])
    # 张三拥有 1 篇公开文档，李四拥有 1 篇私有文档
    db.add_all([
        Document(
            id="doc_zs_public",
            title="张三的公开文档",
            source_type="text",
            is_public=True,
            owner_id="u_zhangsan",
        ),
        Document(
            id="doc_ls_private",
            title="李四的私有文档",
            source_type="text",
            is_public=False,
            owner_id="u_lisi",
        ),
        Document(
            id="doc_ls_public",
            title="李四的公开文档",
            source_type="text",
            is_public=True,
            owner_id="u_lisi",
        ),
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
        yield c

    db.close()
    engine.dispose()


# ---------- 校验层单元语义 ----------

def test_validate_user_id_format_accepts_valid_ids():
    assert validate_user_id_format("u_zhangsan") == "u_zhangsan"
    assert validate_user_id_format("u_lisi") == "u_lisi"


@pytest.mark.parametrize("bad_id", [
    "", "zhangsan", "u_", "u_张三", "u_a b", "u_" + "x" * 100,
])
def test_validate_user_id_format_rejects_bad_ids(bad_id):
    with pytest.raises(HTTPException) as exc:
        validate_user_id_format(bad_id)
    assert exc.value.status_code == 400


# ---------- 接口层：错误语义 ----------

def test_missing_user_id_returns_422(client):
    """缺少 user_id -> 422，不得静默退回张三。"""
    resp = client.get("/api/v1/folders")
    assert resp.status_code == 422


def test_invalid_user_id_format_returns_400(client):
    """格式错误的 user_id -> 400。"""
    resp = client.get("/api/v1/folders", params={"user_id": "not-a-valid-id"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "用户 ID 格式无效"


def test_nonexistent_user_returns_404(client):
    """格式合法但数据库中不存在的用户 -> 404。"""
    resp = client.get("/api/v1/folders", params={"user_id": "u_nobody"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "用户不存在"


# ---------- 接口层：切换用户与个人数据隔离 ----------

def test_switch_user_uses_correct_documents(client):
    """切换用户后，个人文档列表使用该用户的数据。"""
    resp_zs = client.get("/api/v1/documents/all", params={"user_id": "u_zhangsan"})
    resp_ls = client.get("/api/v1/documents/all", params={"user_id": "u_lisi"})

    assert resp_zs.status_code == 200
    assert resp_ls.status_code == 200

    zs_titles = {d["title"] for d in resp_zs.json()}
    ls_titles = {d["title"] for d in resp_ls.json()}

    assert "张三的公开文档" in zs_titles
    assert "李四的私有文档" not in zs_titles
    assert "李四的公开文档" in ls_titles
    assert "张三的公开文档" not in ls_titles


# ---------- 接口层：作者主页目标作者与操作者不混用 ----------

def test_author_profile_uses_path_author_not_current_user(client):
    """
    作者主页路径参数 author_id 是目标作者。
    访问 /users/u_lisi/docs 应返回李四的公开文档，而不是当前用户的文档。
    """
    resp = client.get("/api/v1/users/u_lisi/docs")
    assert resp.status_code == 200

    titles = {d["title"] for d in resp.json()}
    assert "李四的公开文档" in titles  # 目标作者的公开文档
    assert "李四的私有文档" not in titles  # 目标作者的私有文档不公开
    assert "张三的公开文档" not in titles  # 不应返回其他用户的内容

    # 换成张三作者主页，结果只随目标作者变化
    resp_zs = client.get("/api/v1/users/u_zhangsan/docs")
    assert resp_zs.status_code == 200
    titles_zs = {d["title"] for d in resp_zs.json()}
    assert "张三的公开文档" in titles_zs
    assert "李四的公开文档" not in titles_zs


# ---------- #45 补充：18 个接口逐个接入用户上下文的覆盖测试 ----------
# 以下 15 个接口按裁决原则 1~4 接入 get_current_user。
# 每项提供除 user_id 外的完整合法参数，确保 422/404 只由用户上下文校验触发，
# 不会真正进入业务逻辑（因此不会触发 embedding / LLM 等外部调用）。
WIRED_ENDPOINTS = [
    ("get", "/api/v1/search", {"params": {"q": "test"}}),                    # 原则1
    ("post", "/api/v1/agent/ask", {"json": {"question": "test"}}),           # 原则1
    ("post", "/api/v1/tags", {"json": {"name": "tag_x"}}),                   # 原则4
    ("delete", "/api/v1/tags/tag_x", {}),                                    # 原则4
    ("post", "/api/v1/tags/tag_x/pin", {}),                                  # 原则4
    ("post", "/api/v1/documents/doc_x/tags/tag_x", {}),                      # 原则4
    ("delete", "/api/v1/documents/doc_x/tags/tag_x", {}),                    # 原则4
    ("get", "/api/v1/tags/tag_x/documents", {}),                             # 原则4
    ("get", "/api/v1/documents/filter", {}),                                 # 原则2
    ("put", "/api/v1/documents/doc_x/meta", {"json": {"title": "x"}}),       # 原则2
    ("get", "/api/v1/documents/doc_x/content", {}),                          # 原则2
    ("delete", "/api/v1/documents/doc_x", {}),                               # 原则2
    ("get", "/api/v1/folders/folder_x/documents", {}),                       # 原则3
    ("post", "/api/v1/folders/folder_x/documents/doc_x", {}),                # 原则3
    ("delete", "/api/v1/folders/folder_x/documents/doc_x", {}),              # 原则3
]


def _with_user(kwargs, user_id):
    """在请求 kwargs 中注入 user_id 查询参数，保留其他参数。"""
    new = dict(kwargs)
    params = dict(new.get("params", {}))
    params["user_id"] = user_id
    new["params"] = params
    return new


@pytest.mark.parametrize("method,path,kwargs", WIRED_ENDPOINTS)
def test_wired_endpoint_requires_user_id(client, method, path, kwargs):
    """新接入接口：缺失 user_id 一律 422。"""
    resp = client.request(method, path, **kwargs)
    assert resp.status_code == 422, (
        f"{method.upper()} {path} 缺失 user_id 应返回 422，实际 {resp.status_code}"
    )


@pytest.mark.parametrize("method,path,kwargs", WIRED_ENDPOINTS)
def test_wired_endpoint_rejects_nonexistent_user(client, method, path, kwargs):
    """新接入接口：格式合法但不存在的用户返回 404。"""
    resp = client.request(method, path, **_with_user(kwargs, "u_nobody"))
    assert resp.status_code == 404, (
        f"{method.upper()} {path} 不存在用户应返回 404，实际 {resp.status_code}"
    )


# 以下接口按裁决原则 5/6 不接入用户上下文：不传 user_id 仍可正常访问。
PUBLIC_ENDPOINTS = [
    "/api/v1/tags",                                # 原则6：全局标签列表
    "/api/v1/square/folders/folder_x/docs",        # 原则5：公开文件夹浏览
    # 作者主页（原则5）已由 test_author_profile_uses_path_author_not_current_user 覆盖
]


@pytest.mark.parametrize("path", PUBLIC_ENDPOINTS)
def test_public_endpoints_do_not_require_user_id(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, (
        f"{path} 不应强制要求 user_id，实际 {resp.status_code}"
    )
