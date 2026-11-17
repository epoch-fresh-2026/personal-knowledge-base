"""Issue #54 工程整理回归测试：路由拆分 / 删除逻辑迁移 / 可见性规则收敛。

目标：证明「重构前后业务行为一致」——
- API 路径/方法契约与拆分前完全相同（冻结清单）；
- api/router.py 只做汇总注册，业务实现不在 api 层；
- 文档删除生命周期从 folder_service 迁入 document_service，且旧位置不再导出；
- #49 收藏与 #50 正文共用同一可见性口径，行为不变。

所有数据库用例使用独立内存 SQLite（StaticPool），不触碰真实 backend/pkb.db。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base, get_db
from modules.ingest.domain.models import User, Document
from modules.manage.domain.models import Folder
from api.router import api_router


# 拆分前的 API 契约冻结清单（路径 -> 方法集合），来自 #53 验收时的 OpenAPI 快照。
EXPECTED_ROUTES = {
    "/api/v1/agent/ask": {"POST"},
    "/api/v1/documents/all": {"GET"},
    "/api/v1/documents/filter": {"GET"},
    "/api/v1/documents/uncategorized": {"GET"},
    "/api/v1/documents/upload": {"POST"},
    "/api/v1/documents/url": {"POST"},
    "/api/v1/documents/{doc_id}": {"DELETE"},
    "/api/v1/documents/{doc_id}/content": {"GET"},
    "/api/v1/documents/{doc_id}/meta": {"PUT"},
    "/api/v1/documents/{doc_id}/permanent": {"DELETE"},
    "/api/v1/documents/{doc_id}/restore": {"POST"},
    "/api/v1/documents/{doc_id}/tags/{tag_id}": {"DELETE", "POST"},
    "/api/v1/documents/{doc_id}/toggle-visibility": {"POST"},
    "/api/v1/favorites": {"GET"},
    "/api/v1/favorites/doc/{doc_id}": {"POST"},
    "/api/v1/favorites/folder/{folder_id}": {"POST"},
    "/api/v1/folders": {"GET", "POST"},
    "/api/v1/folders/{folder_id}": {"DELETE"},
    "/api/v1/folders/{folder_id}/documents": {"GET"},
    "/api/v1/folders/{folder_id}/documents/{doc_id}": {"DELETE", "POST"},
    "/api/v1/folders/{folder_id}/name": {"PUT"},
    "/api/v1/folders/{folder_id}/toggle-public": {"POST"},
    "/api/v1/mistakes": {"GET", "POST"},
    "/api/v1/mistakes/analytics/overview": {"GET"},
    "/api/v1/mistakes/analytics/trends": {"GET"},
    "/api/v1/mistakes/knowledge-points": {"GET"},
    "/api/v1/mistakes/recommendations": {"GET"},
    "/api/v1/mistakes/{mistake_id}": {"DELETE", "PUT"},
    "/api/v1/mistakes/{mistake_id}/review": {"POST"},
    "/api/v1/mistakes/{mistake_id}/status": {"PATCH"},
    "/api/v1/search": {"GET"},
    "/api/v1/square": {"GET"},
    "/api/v1/square/folders": {"GET"},
    "/api/v1/square/folders/{folder_id}/docs": {"GET"},
    "/api/v1/tags": {"GET", "POST"},
    "/api/v1/tags/{tag_id}": {"DELETE"},
    "/api/v1/tags/{tag_id}/pin": {"POST"},
    "/api/v1/tags/{tag_name}/documents": {"GET"},
    "/api/v1/users/{author_id}/docs": {"GET"},
}


def test_route_contract_unchanged_after_split():
    """路由拆分后 API 路径与方法契约与拆分前一致。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    with TestClient(app) as c:  # noqa: F841 - 触发应用启动/路由展开
        spec = app.openapi()
    actual = {
        path: {m.upper() for m in ops}
        for path, ops in spec["paths"].items()
    }
    assert actual == EXPECTED_ROUTES, (
        f"缺失或变更: {set(EXPECTED_ROUTES) - set(actual)} / "
        f"新增: {set(actual) - set(EXPECTED_ROUTES)}"
    )


def test_api_router_only_aggregates():
    """api/router.py 只 import APIRouter 与各域 router，不含 pydantic/Service/DB 业务依赖。"""
    import inspect
    import api.router as module

    src = inspect.getsource(module)
    # 不应出现业务实现标志（请求模型、依赖、Service 调用、db.Session）
    for forbidden in ("BaseModel", "Depends(", "Query(", "db.query", "HTTPException"):
        assert forbidden not in src, f"api 层仍含业务实现痕迹: {forbidden}"
    # 应包含五个域 router 的注册
    for name in ("ingest_router", "retrieve_router", "agent_router",
                 "manage_router", "mistake_router"):
        assert name in src
        assert hasattr(module, name)


def test_deletion_lifecycle_moved_to_document_service():
    """删除生命周期可从 document_service 导入，且不再从 folder_service 导出。"""
    from modules.manage.service import document_service as ds
    from modules.manage.service import folder_service as fs

    for name in (
        "delete_document", "restore_document", "permanent_delete_document",
        "register_cleanup_intent", "confirm_cleanup_intent",
        "clear_cleanup_intent", "retry_orphan_file_cleanup",
        "record_orphan_file", "_safe_upload_rel_path",
    ):
        assert hasattr(ds, name), f"document_service 缺少 {name}"
        assert not hasattr(fs, name), f"folder_service 仍导出 {name}（迁移未完成）"


def test_visibility_rule_single_definition_and_behavior():
    """可见性口径收敛到 document_service，且 #49/#50 复用同一函数；行为与旧式判断一致。"""
    from modules.manage.service.document_service import is_document_visible_to_user
    import modules.manage.service.folder_service as fs
    import modules.manage.controller.router as ctrl

    # 三者持有同一个函数对象（单一定义，非复制粘贴）
    assert fs.is_document_visible_to_user is is_document_visible_to_user
    assert ctrl.is_document_visible_to_user is is_document_visible_to_user

    owner, other = "u_a", "u_b"
    cases = [
        (False, owner, False, True),   # 未删除 + 所有者 -> 可见
        (False, other, True, True),    # 未删除 + 他人但公开 -> 可见
        (False, other, False, False),  # 未删除 + 他人私有 -> 不可见
        (True, owner, True, False),    # 已删除 -> 不可见（即使所有者/公开）
    ]
    for is_deleted, uid, is_public, expected in cases:
        doc = Document(id="d", title="t", source_type="file",
                       owner_id=owner, is_deleted=is_deleted, is_public=is_public)
        # 与旧式判断逐项比对，证明行为一致
        legacy = (not is_deleted) and (doc.owner_id == uid or is_public)
        assert is_document_visible_to_user(doc, uid) == expected
        assert is_document_visible_to_user(doc, uid) == legacy


def test_delete_restore_permanent_via_api_still_works():
    """拆分与迁移后，删除→恢复→永久删除的 API 行为保持不变（临时库）。"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    db.add_all([
        User(id="u_a", nickname="A"),
        User(id="u_b", nickname="B"),
        Document(id="d1", title="t", source_type="file", owner_id="u_a",
                 is_public=True, is_deleted=False),
    ])
    db.commit()

    def override_get_db():
        yield db

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        # 软删除
        r = client.delete("/api/v1/documents/d1", params={"user_id": "u_a"})
        assert r.status_code == 200 and r.json()["is_deleted"] is True
        assert db.query(Document).filter(Document.id == "d1").first().is_deleted is True
        # 软删除后正文不可读（所有者亦不可）
        assert client.get("/api/v1/documents/d1/content",
                          params={"user_id": "u_a"}).status_code == 404
        # 恢复
        r = client.post("/api/v1/documents/d1/restore", params={"user_id": "u_a"})
        assert r.status_code == 200 and r.json()["is_deleted"] is False
        assert client.get("/api/v1/documents/d1/content",
                          params={"user_id": "u_a"}).status_code == 200
        # 非所有者不能删除
        assert client.delete("/api/v1/documents/d1",
                             params={"user_id": "u_b"}).json().get("error")
        # 再软删后永久删除（无本地文件 -> file_cleanup not_applicable）
        client.delete("/api/v1/documents/d1", params={"user_id": "u_a"})
        r = client.delete("/api/v1/documents/d1/permanent", params={"user_id": "u_a"})
        assert r.status_code == 200 and r.json()["status"] == "success"
        assert db.query(Document).filter(Document.id == "d1").first() is None
    db.close()
    engine.dispose()
