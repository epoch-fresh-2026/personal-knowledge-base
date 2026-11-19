"""Issue #46：统一搜索范围与用户数据隔离的回归测试。

三个入口（GET /search、POST /agent/ask、GET /documents/filter）统一使用
「本人文档（含私有）+ 他人公开文档；排除他人私有与所有软删除文档」的访问口径。

覆盖：
1. 检索自己的私有文档；2. 检索他人公开文档；3. 不能检索他人私有文档；
4. 软删除文档不出现在结果；5. Agent 多轮检索每轮都携带当前用户、无法绕过范围；
6. /documents/filter 篡改 owner_id 不能取他人私有；7. 能取允许的公开文档；
8. 跨用户数据隔离；9. 无效用户上下文不退化成默认用户或无限制查询。

所有测试使用独立内存 SQLite（StaticPool）+ dependency_overrides，
不触碰真实 pkb.db，也不访问真实 uploads 目录。
"""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base, get_db
from shared.document_visibility import (
    UserScopeRequiredError,
    require_user_id,
    visible_document_condition,
)
from modules.ingest.domain.models import User, Document, Chunk
from modules.retrieve.repository import chunk_repo
from modules.manage.service import document_service
from api.router import api_router
from modules.retrieve.service import search as search_service
from modules.agent.service import agent_service
import modules.agent.controller.router as agent_router


@pytest.fixture
def ctx(monkeypatch):
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
        User(id="u_wangwu", nickname="王五"),
    ])
    docs = [
        Document(id="doc_zs_private", title="张三私有", source_type="text",
                 is_public=False, is_deleted=False, owner_id="u_zhangsan"),
        Document(id="doc_zs_public", title="张三公开", source_type="text",
                 is_public=True, is_deleted=False, owner_id="u_zhangsan"),
        Document(id="doc_ls_private", title="李四私有", source_type="text",
                 is_public=False, is_deleted=False, owner_id="u_lisi"),
        Document(id="doc_ls_public", title="李四公开", source_type="text",
                 is_public=True, is_deleted=False, owner_id="u_lisi"),
        Document(id="doc_zs_deleted", title="张三已删公开", source_type="text",
                 is_public=True, is_deleted=True, owner_id="u_zhangsan"),
        Document(id="doc_ls_deleted", title="李四已删私有", source_type="text",
                 is_public=False, is_deleted=True, owner_id="u_lisi"),
    ]
    db.add_all(docs)
    # 每个文档一个 chunk，embedding 与查询向量同向，content 含关键词“知识库”。
    db.add_all([
        Chunk(id=f"c_{d.id}", document_id=d.id, content=f"知识库内容：{d.title}",
              embedding=json.dumps([1.0, 0.0]), chunk_index=0)
        for d in docs
    ])
    db.commit()

    # 固定查询向量，避免调用真实向量服务；维度与 chunk 一致。
    async def fake_get_embedding(text):
        return [1.0, 0.0]
    monkeypatch.setattr(search_service, "get_embedding", fake_get_embedding)

    def override_get_db():
        yield db

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c, db

    db.close()
    engine.dispose()


def _result_doc_ids(client, user_id, q="知识库", top_k=20):
    resp = client.get("/api/v1/search", params={
        "q": q, "user_id": user_id, "top_k": top_k,
    })
    assert resp.status_code == 200, resp.text
    return {item["document_id"] for item in resp.json()["results"]}


def _filter_ids(client, user_id, **params):
    params["user_id"] = user_id
    resp = client.get("/api/v1/documents/filter", params=params)
    assert resp.status_code == 200, resp.text
    return {item["id"] for item in resp.json()}


# ---------- 搜索入口 ----------

def test_search_returns_own_private_doc(ctx):
    """1. 用户能检索到自己的私有文档。"""
    client, _ = ctx
    ids = _result_doc_ids(client, "u_zhangsan")
    assert "doc_zs_private" in ids


def test_search_returns_others_public_doc(ctx):
    """2. 用户能检索到他人的公开文档。"""
    client, _ = ctx
    ids = _result_doc_ids(client, "u_zhangsan")
    assert "doc_ls_public" in ids


def test_search_excludes_others_private_doc(ctx):
    """3. 用户不能检索到他人的私有文档。"""
    client, _ = ctx
    ids = _result_doc_ids(client, "u_zhangsan")
    assert "doc_ls_private" not in ids


def test_search_excludes_soft_deleted_docs(ctx):
    """4. 软删除文档（含本人/他人、公开/私有）一律不出现在检索结果。"""
    client, _ = ctx
    ids = _result_doc_ids(client, "u_zhangsan")
    assert "doc_zs_deleted" not in ids
    assert "doc_ls_deleted" not in ids


def test_search_scope_is_exact_for_zhang(ctx):
    """综合：张三的可见集合恰为本人未删 + 他人公开。"""
    client, _ = ctx
    assert _result_doc_ids(client, "u_zhangsan") == {
        "doc_zs_private", "doc_zs_public", "doc_ls_public",
    }


# ---------- Agent 入口：多轮检索 ----------

def test_agent_all_rounds_keep_access_scope(ctx, monkeypatch):
    """5. Agent 多轮检索每一轮都携带当前用户，且结果不含他人私有/软删。"""
    client, _ = ctx

    # 强制走完两轮：第一轮判定不足 -> refine -> 第二轮检索。
    suff = {"n": 0}
    def fake_is_sufficient(chunks):
        suff["n"] += 1
        return suff["n"] >= 2
    monkeypatch.setattr(agent_service, "is_sufficient", fake_is_sufficient)

    async def fake_chat_completion(prompt):
        if "上一次使用的检索词" in prompt:
            return "知识库 二次"
        return "知识库 改写"

    async def fake_generate_answer(question, chunks):
        return "根据资料回答。[1]"

    monkeypatch.setattr(agent_service, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(agent_service, "generate_answer", fake_generate_answer)

    # spy 包裹 retrieve_adapter 使用的 search，记录每轮注入的 user_id，
    # 并委托给真实 search（真实内存库 + 真实可见条件）。
    real_search = agent_router.search
    seen_user_ids = []

    async def spy_search(db, query, user_id=None, top_k=5):
        seen_user_ids.append(user_id)
        return await real_search(db, query, user_id=user_id, top_k=top_k)

    monkeypatch.setattr(agent_router, "search", spy_search)

    resp = client.post(
        "/api/v1/agent/ask",
        json={"question": "知识库内容"},
        params={"user_id": "u_zhangsan"},
    )
    assert resp.status_code == 200, resp.text

    # 至少发生两轮检索，且每一轮的 user_id 都是当前用户。
    assert len(seen_user_ids) >= 2
    assert all(uid == "u_zhangsan" for uid in seen_user_ids)

    body = resp.json()
    source_docs = {item["document_id"] for item in body["sources"]}
    assert "doc_ls_private" not in source_docs
    assert "doc_zs_deleted" not in source_docs
    assert "doc_ls_deleted" not in source_docs


# ---------- 文档筛选入口 ----------

def test_filter_owner_id_cannot_expose_others_private(ctx):
    """6. 篡改 owner_id 为他人，仍不能获取他人私有文档。"""
    client, _ = ctx
    ids = _filter_ids(client, "u_zhangsan", owner_id="u_lisi")
    assert "doc_ls_private" not in ids
    assert "doc_ls_deleted" not in ids


def test_filter_owner_id_returns_allowed_public(ctx):
    """7. 篡改 owner_id 为他人时，仍能获取其公开未删文档。"""
    client, _ = ctx
    ids = _filter_ids(client, "u_zhangsan", owner_id="u_lisi")
    assert "doc_ls_public" in ids


def test_filter_own_owner_id_returns_own_private(ctx):
    """补充：owner_id 指向自己时可见私有文档。"""
    client, _ = ctx
    ids = _filter_ids(client, "u_zhangsan", owner_id="u_zhangsan")
    assert "doc_zs_private" in ids
    assert "doc_ls_public" not in ids  # 限定 owner 后不含他人文档


def test_filter_without_owner_id_is_full_visible_set(ctx):
    """补充：不传 owner_id 时返回完整可见集合。"""
    client, _ = ctx
    assert _filter_ids(client, "u_zhangsan") == {
        "doc_zs_private", "doc_zs_public", "doc_ls_public",
    }


# ---------- 跨用户隔离 ----------

@pytest.mark.parametrize("user_id,expected", [
    ("u_zhangsan", {"doc_zs_private", "doc_zs_public", "doc_ls_public"}),
    ("u_lisi", {"doc_ls_private", "doc_ls_public", "doc_zs_public"}),
    ("u_wangwu", {"doc_zs_public", "doc_ls_public"}),
])
def test_cross_user_isolation(ctx, user_id, expected):
    """8. 不同用户之间的可见集合正确隔离（wangwu 无私有、只见两份公开）。"""
    client, _ = ctx
    assert _result_doc_ids(client, user_id) == expected


# ---------- 无效用户上下文 ----------

@pytest.mark.parametrize("method,path,extra", [
    ("get", "/api/v1/search", {"params": {"q": "知识库"}}),
    ("post", "/api/v1/agent/ask", {"json": {"question": "知识库"}}),
    ("get", "/api/v1/documents/filter", {}),
])
def test_invalid_user_context_never_falls_back_to_unrestricted(ctx, method, path, extra):
    """9. 无效上下文：缺失 422 / 格式错 400 / 不存在 404，不退化成默认用户。"""
    client, _ = ctx
    # 缺失 user_id
    resp = client.request(method, path, **extra)
    assert resp.status_code == 422, (method, path, resp.text)

    # 格式错误
    bad = dict(extra)
    params = dict(bad.get("params", {}))
    params["user_id"] = "not-valid"
    bad["params"] = params
    resp = client.request(method, path, **bad)
    assert resp.status_code == 400, (method, path, resp.text)

    # 格式合法但不存在
    params["user_id"] = "u_nobody"
    bad["params"] = params
    resp = client.request(method, path, **bad)
    assert resp.status_code == 404, (method, path, resp.text)


# ---------- fail-closed：服务层拒绝无效用户上下文 ----------

@pytest.mark.parametrize("bad_uid", [None, "", "   ", 123, "bad-format", "u_"])
def test_require_user_id_rejects_invalid(bad_uid):
    """守卫对 None/空/非字符串/格式错误一律拒绝（fail-closed）。"""
    with pytest.raises(UserScopeRequiredError):
        require_user_id(bad_uid)


def test_require_user_id_accepts_valid():
    assert require_user_id("u_zhangsan") == "u_zhangsan"


def test_visible_document_condition_rejects_missing_user():
    """SQL 条件构造也要 fail-closed，不生成无范围条件。"""
    with pytest.raises(UserScopeRequiredError):
        visible_document_condition(None)


def test_service_search_rejects_missing_user(ctx):
    """search() 缺失 user_id 直接拒绝，不返回任何数据。"""
    _, db = ctx
    with pytest.raises(UserScopeRequiredError):
        asyncio.run(search_service.search(db, "知识库", user_id=None, top_k=20))


@pytest.mark.parametrize("bad_uid", [None, "", "not-valid"])
def test_service_search_rejects_invalid_user(ctx, bad_uid):
    """search() 无效 user_id 不会退化为全局查询。"""
    _, db = ctx
    with pytest.raises(UserScopeRequiredError):
        asyncio.run(search_service.search(db, "知识库", user_id=bad_uid, top_k=20))


def test_service_keyword_search_rejects_missing_user(ctx):
    """search_by_keywords() 缺失 user_id 直接拒绝。"""
    _, db = ctx
    with pytest.raises(UserScopeRequiredError):
        chunk_repo.search_by_keywords(db, ["知识库"], user_id=None, top_k=20)


def test_service_list_documents_rejects_missing_user(ctx):
    """list_documents() 缺失 user_id 直接拒绝，不返回全局文档。"""
    _, db = ctx
    with pytest.raises(UserScopeRequiredError):
        document_service.list_documents(db, {}, user_id=None)


def test_keyword_search_applies_user_scope(ctx):
    """关键词检索路径（Embedding 失败降级场景）也执行用户范围过滤。

    把 get_embedding 置为异常，强制只剩关键词路径，验证他人私有与软删不可见。
    """
    client, _ = ctx
    # ctx 已把 get_embedding 固定为成功向量；此处覆盖为异常，强制关键词路径。
    async def failing_embedding(text):
        raise RuntimeError("Embedding 不可用")
    import modules.retrieve.service.search as search_mod
    original = search_mod.get_embedding
    search_mod.get_embedding = failing_embedding
    try:
        ids = _result_doc_ids(client, "u_zhangsan")
        assert "doc_zs_private" in ids
        assert "doc_ls_public" in ids
        assert "doc_ls_private" not in ids
        assert "doc_zs_deleted" not in ids
        assert "doc_ls_deleted" not in ids
    finally:
        search_mod.get_embedding = original


def test_semantic_search_applies_user_scope(ctx):
    """语义检索路径同样执行用户范围过滤（他人私有/软删不可见）。"""
    client, _ = ctx
    ids = _result_doc_ids(client, "u_lisi")
    assert "doc_ls_private" in ids       # 自己的私有
    assert "doc_zs_public" in ids        # 他人公开
    assert "doc_zs_private" not in ids   # 他人私有
    assert "doc_zs_deleted" not in ids
    assert "doc_ls_deleted" not in ids
