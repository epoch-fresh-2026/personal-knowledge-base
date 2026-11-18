"""Issue #47 补充核查测试：孤立文件追踪/重试、恢复完整性、软删除过滤与迁移健壮性。

本文件为补充测试，不改动原有 test_document_lifecycle.py。
使用独立内存 SQLite + monkeypatch 清单路径/文件系统，不触碰真实数据库与 uploads。
"""

import json
import os

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
# Issue #54：文档删除生命周期及其孤立文件补偿已迁入 document_service。
import modules.manage.service.document_service as ds
from modules.manage.service.document_service import (
    _safe_upload_rel_path,
    retry_orphan_file_cleanup,
)
from modules.ingest.service import reindex_service

# 兼容原测试中的 fs 别名（现指向文档服务），保持断言与 monkeypatch 语义不变。
fs = ds


def _make_doc(doc_id, owner, title, public=False, deleted=False, source_url=None):
    return Document(
        id=doc_id, title=title, source_type="file", source_url=source_url,
        is_public=public, owner_id=owner, is_deleted=deleted,
    )


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """内存库 + 客户端；把孤立文件清单与 uploads 目录隔离到 tmp_path。"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()

    db.add_all([
        User(id="u_zhangsan", nickname="张三"),
        User(id="u_lisi", nickname="李四"),
    ])
    db.add(_make_doc(
        "doc_del", "u_zhangsan", "待彻底删除", deleted=True,
        source_url="/uploads/orphan_test_file.txt",
    ))
    db.add(_make_doc(
        "doc_lisi_del", "u_lisi", "李四已删文档", deleted=True,
        source_url="/uploads/lisi_file.txt",
    ))
    db.add(_make_doc("doc_active", "u_zhangsan", "活跃文档"))
    db.add(Chunk(id="ck1", document_id="doc_del", content="正文", embedding=None, chunk_index=0))
    db.add(Folder(id="f1", name="文件夹", owner_id="u_zhangsan", is_public=False))
    db.add(DocumentFolder(document_id="doc_del", folder_id="f1"))
    db.add(Tag(id="t1", name="标签", pinned=False))
    db.add(DocumentTag(document_id="doc_del", tag_id="t1"))
    db.add(FavoriteDocument(user_id="u_zhangsan", document_id="doc_del"))
    db.commit()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    # 隔离文件系统： uploads 与清单都指向 tmp
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(fs, "ORPHAN_CLEANUP_FILE", str(upload_dir / ".orphan_cleanup.json"))
    monkeypatch.chdir(tmp_path)

    with TestClient(app) as c:
        yield c, db, upload_dir

    db.close()
    engine.dispose()


# ---------- 问题1：孤立文件追踪 / 重试 / 幂等 / 误删防护 ----------

def test_safe_upload_rel_path_rejects_traversal():
    """路径穿越、子目录、绝对路径、外部 URL 均被拒绝，避免误删。"""
    assert _safe_upload_rel_path("/uploads/a.txt") == "a.txt"
    assert _safe_upload_rel_path("/uploads/a_b.md") == "a_b.md"
    assert _safe_upload_rel_path("/uploads/../../etc/passwd") is None
    assert _safe_upload_rel_path("/uploads/sub/a.txt") is None
    assert _safe_upload_rel_path("/uploads/a\\b.txt") is None
    assert _safe_upload_rel_path("/absolute/path") is None
    assert _safe_upload_rel_path("http://x/y.txt") is None
    assert _safe_upload_rel_path(None) is None


def test_orphan_file_recorded_when_cleanup_fails(ctx, monkeypatch):
    """数据库删除成功但文件清理失败时，写入持久化清单（可追踪）。"""
    client, db, upload_dir = ctx
    make_it = upload_dir / "orphan_test_file.txt"
    make_it.write_text("content", encoding="utf-8")

    def boom(path):
        raise OSError("磁盘只读")

    monkeypatch.setattr(fs.os, "remove", boom)
    resp = client.delete("/api/v1/documents/doc_del/permanent", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert "failed" in resp.json()["file_cleanup"]
    # 数据库已删
    assert db.query(Document).filter(Document.id == "doc_del").first() is None
    # 清单已登记（持久化可追踪）
    entry_file = upload_dir / ".orphan_cleanup.json"
    assert entry_file.exists()
    entries = json.loads(entry_file.read_text(encoding="utf-8"))
    assert any(e["doc_id"] == "doc_del" and e["path"] == "orphan_test_file.txt" for e in entries)


def test_orphan_cleanup_retry_is_idempotent(ctx):
    """重复重试幂等：文件不存在视为成功，第二次不重复计数、不误删。"""
    client, db, upload_dir = ctx
    entry_file = upload_dir / ".orphan_cleanup.json"
    # 清单中有两条：一条文件已不存在，一条仍存在
    victim = upload_dir / "victim.txt"
    victim.write_text("x", encoding="utf-8")
    entry_file.write_text(json.dumps([
        {"doc_id": "d1", "path": "already_gone.txt"},
        {"doc_id": "d2", "path": "victim.txt"},
    ], ensure_ascii=False), encoding="utf-8")

    first = retry_orphan_file_cleanup()
    assert first == {"attempted": 2, "cleaned": 2, "remaining": 0}
    assert not victim.exists()
    # 清单已清空
    assert json.loads(entry_file.read_text(encoding="utf-8")) == []

    second = retry_orphan_file_cleanup()
    assert second == {"attempted": 0, "cleaned": 0, "remaining": 0}


def test_orphan_cleanup_keeps_failed_and_drops_illegal_paths(ctx, monkeypatch):
    """删除仍失败则保留在清单；非法路径条目被丢弃而不尝试删除。"""
    client, db, upload_dir = ctx
    entry_file = upload_dir / ".orphan_cleanup.json"
    stuck = upload_dir / "stuck.txt"
    stuck.write_text("x", encoding="utf-8")
    entry_file.write_text(json.dumps([
        {"doc_id": "d1", "path": "stuck.txt"},
        {"doc_id": "d2", "path": "../../important.txt"},  # 非法路径
    ], ensure_ascii=False), encoding="utf-8")

    def boom(path):
        raise OSError("still failing")

    monkeypatch.setattr(fs.os, "remove", boom)
    result = retry_orphan_file_cleanup()
    # 非法路径被丢弃（不计入 attempted），stuck 仍失败保留
    assert result["attempted"] == 1
    assert result["cleaned"] == 0
    assert result["remaining"] == 1
    remaining = json.loads(entry_file.read_text(encoding="utf-8"))
    assert [e["path"] for e in remaining] == ["stuck.txt"]


def test_permanent_delete_self_heals_history(ctx, monkeypatch):
    """每次彻底删除前自愈重试历史清单中的孤立文件。"""
    client, db, upload_dir = ctx
    entry_file = upload_dir / ".orphan_cleanup.json"
    leftover = upload_dir / "leftover.txt"
    leftover.write_text("x", encoding="utf-8")
    entry_file.write_text(json.dumps([
        {"doc_id": "old", "path": "leftover.txt"},
    ], ensure_ascii=False), encoding="utf-8")

    # 正常删除（文件删除成功），但开头已自愈清掉历史的 leftover
    resp = client.delete("/api/v1/documents/doc_lisi_del/permanent", params={"user_id": "u_lisi"})
    assert resp.status_code == 200
    assert not leftover.exists()
    assert json.loads(entry_file.read_text(encoding="utf-8")) == []


# ---------- 问题2：恢复完整性 ----------

def test_restore_keeps_chunks_file_and_relations(ctx, monkeypatch):
    """恢复后 Chunk/Embedding/文件/文件夹关联完整，仅状态位改变。"""
    client, db, upload_dir = ctx
    target = upload_dir / "orphan_test_file.txt"
    target.write_text("file", encoding="utf-8")

    # 给 chunk 一个 embedding 以验证恢复不动向量
    ck = db.query(Chunk).filter(Chunk.id == "ck1").first()
    ck.embedding = "[0.1,0.2]"
    db.commit()

    resp = client.post("/api/v1/documents/doc_del/restore", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 200
    assert resp.json()["is_deleted"] is False
    doc = db.query(Document).filter(Document.id == "doc_del").first()
    assert doc.is_deleted is False and doc.deleted_at is None
    # 关联数据完整
    assert db.query(Chunk).filter(Chunk.document_id == "doc_del").count() == 1
    assert db.query(Chunk).filter(Chunk.id == "ck1").first().embedding == "[0.1,0.2]"
    assert db.query(DocumentFolder).filter(DocumentFolder.document_id == "doc_del").count() == 1
    assert db.query(DocumentTag).filter(DocumentTag.document_id == "doc_del").count() == 1
    assert db.query(FavoriteDocument).filter(FavoriteDocument.document_id == "doc_del").count() == 1
    assert target.exists()  # 文件未被恢复流程破坏


def test_restore_permissions_and_repeat(ctx):
    """非所有者不能恢复；重复恢复有明确结果；已彻底删除不可恢复。"""
    client, db, upload_dir = ctx
    # 非所有者
    resp = client.post("/api/v1/documents/doc_del/restore", params={"user_id": "u_lisi"})
    assert resp.json().get("error") == "文档不存在或无权操作"
    assert db.query(Document).filter(Document.id == "doc_del").first().is_deleted is True

    # 所有者恢复成功
    resp = client.post("/api/v1/documents/doc_del/restore", params={"user_id": "u_zhangsan"})
    assert resp.json()["is_deleted"] is False
    # 重复恢复：文档已是未删除态，找不到匹配 is_deleted=True 的记录 -> 明确 error
    resp2 = client.post("/api/v1/documents/doc_del/restore", params={"user_id": "u_zhangsan"})
    assert resp2.json().get("error") == "文档不存在或无权操作"

    # 已彻底删除的文档不可恢复
    client.delete("/api/v1/documents/doc_del/permanent", params={"user_id": "u_zhangsan"})
    make_it = upload_dir / "orphan_test_file.txt"
    make_it.write_text("x", encoding="utf-8")
    client.delete("/api/v1/documents/doc_del/permanent", params={"user_id": "u_zhangsan"})
    resp3 = client.post("/api/v1/documents/doc_del/restore", params={"user_id": "u_zhangsan"})
    assert resp3.json().get("error") == "文档不存在或无权操作"


# ---------- 问题3：reindex 软删除过滤 ----------

def test_reindex_rejects_soft_deleted_document(ctx, monkeypatch):
    """已软删除文档不允许 reindex（过滤完整性补全）。"""
    client, db, upload_dir = ctx
    import asyncio

    async def fake_embeddings(chunks):
        return None

    monkeypatch.setattr(reindex_service, "generate_chunk_embeddings", fake_embeddings)
    with pytest.raises(ValueError) as exc:
        asyncio.run(reindex_service.reindex_document(db, "doc_del", "新正文内容"))
    assert "文档不存在" in str(exc.value)


# ---------- 问题4：迁移脚本健壮性 ----------

def test_migration_is_idempotent_and_preserves_data():
    """迁移脚本可重复执行、兼容已有数据、不覆盖字段、正确处理默认值。"""
    import tempfile
    from sqlalchemy import text as sa_text

    db_file = os.path.join(tempfile.mkdtemp(), "mig_test.db")
    # 构造迁移前的表（无软删除字段）+ 一条已有数据
    engine = create_engine(f"sqlite:///{db_file}")
    with engine.begin() as conn:
        conn.execute(sa_text(
            "CREATE TABLE documents (id VARCHAR PRIMARY KEY, title VARCHAR, "
            "is_public BOOLEAN, owner_id VARCHAR, created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(sa_text(
            "INSERT INTO documents (id, title, is_public, owner_id) "
            "VALUES ('d1', '旧文档', 1, 'u1')"
        ))

    # 直接复用迁移 SQL 逻辑（不依赖全局 engine），执行两次验证幂等
    def apply_migration(eng):
        insp_columns = {c["name"] for c in __import__("sqlalchemy").inspect(eng).get_columns("documents")}
        with eng.begin() as conn:
            if "is_deleted" not in insp_columns:
                conn.execute(sa_text("ALTER TABLE documents ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"))
            if "deleted_at" not in insp_columns:
                conn.execute(sa_text("ALTER TABLE documents ADD COLUMN deleted_at DATETIME"))

    apply_migration(engine)
    apply_migration(engine)  # 幂等复跑

    with engine.connect() as conn:
        cols = {c["name"] for c in __import__("sqlalchemy").inspect(engine).get_columns("documents")}
        assert {"is_deleted", "deleted_at"} <= cols
        row = conn.execute(sa_text("SELECT title, is_public, is_deleted, deleted_at FROM documents WHERE id='d1'")).fetchone()
        assert row.title == "旧文档" and row.is_public == 1
        assert row.is_deleted == 0 and row.deleted_at is None  # 默认值/NULL 正确
    engine.dispose()


# ---------- 最后补充核查：清单可靠性（预登记 / 原子替换 / 崩溃恢复） ----------

def test_manifest_write_failure_aborts_delete_and_keeps_file_tracked(ctx, monkeypatch):
    """清单写入失败时中止彻底删除：DB 记录与物理文件都保留，不产生不可追踪的孤立文件。"""
    client, db, upload_dir = ctx
    target = upload_dir / "orphan_test_file.txt"
    target.write_text("content", encoding="utf-8")

    def boom(entries):
        raise OSError("磁盘只读")

    monkeypatch.setattr(fs, "_save_orphan_cleanup", boom)
    resp = client.delete("/api/v1/documents/doc_del/permanent", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 200
    assert "error" in resp.json()
    assert "无法登记" in resp.json()["error"]
    # 未进入 DB 删除阶段：文档与文件都在，不存在「无人知晓」的孤立文件
    assert db.query(Document).filter(Document.id == "doc_del").first() is not None
    assert target.exists()


def test_intent_recovers_after_db_delete_crash(ctx):
    """DB 已删、进程在文件清理前崩溃：pending 意图由 retry(db) 确认并清理文件。"""
    client, db, upload_dir = ctx
    target = upload_dir / "orphan_test_file.txt"
    target.write_text("x", encoding="utf-8")
    entry_file = upload_dir / ".orphan_cleanup.json"
    entry_file.write_text(json.dumps([
        {"doc_id": "doc_del", "path": "orphan_test_file.txt", "phase": fs._PHASE_PENDING}
    ], ensure_ascii=False), encoding="utf-8")

    # 模拟数据库删除已提交、但物理文件尚未处理
    db.query(Document).filter(Document.id == "doc_del").delete()
    db.commit()
    assert db.query(Document).filter(Document.id == "doc_del").first() is None

    result = retry_orphan_file_cleanup(db)
    assert result == {"attempted": 1, "cleaned": 1, "remaining": 0}
    assert not target.exists()
    assert json.loads(entry_file.read_text(encoding="utf-8")) == []


def test_pending_intent_for_existing_doc_is_revoked_without_deleting_file(ctx):
    """预登记后、DB 删除前崩溃：文档仍在库中，retry(db) 撤销意图且绝不删除文件。"""
    client, db, upload_dir = ctx
    target = upload_dir / "orphan_test_file.txt"
    target.write_text("keep me", encoding="utf-8")
    entry_file = upload_dir / ".orphan_cleanup.json"
    entry_file.write_text(json.dumps([
        {"doc_id": "doc_del", "path": "orphan_test_file.txt", "phase": fs._PHASE_PENDING}
    ], ensure_ascii=False), encoding="utf-8")
    assert db.query(Document).filter(Document.id == "doc_del").first() is not None

    result = retry_orphan_file_cleanup(db)
    assert result == {"attempted": 0, "cleaned": 0, "remaining": 0}
    # 核心防误删断言：文档尚在，文件必须原样保留
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "keep me"
    assert json.loads(entry_file.read_text(encoding="utf-8")) == []


def test_pending_intent_without_db_is_kept_and_file_untouched(ctx):
    """无 db 上下文时 pending 条目保守保留，绝不盲删可能仍被文档引用的文件。"""
    client, db, upload_dir = ctx
    target = upload_dir / "orphan_test_file.txt"
    target.write_text("keep me", encoding="utf-8")
    entry_file = upload_dir / ".orphan_cleanup.json"
    pending = [{"doc_id": "doc_del", "path": "orphan_test_file.txt", "phase": fs._PHASE_PENDING}]
    entry_file.write_text(json.dumps(pending, ensure_ascii=False), encoding="utf-8")

    result = retry_orphan_file_cleanup()  # 不传 db
    assert result == {"attempted": 0, "cleaned": 0, "remaining": 1}
    assert target.exists()
    assert json.loads(entry_file.read_text(encoding="utf-8")) == pending


def test_manifest_write_uses_atomic_replace_and_leaves_no_tmp(ctx, monkeypatch):
    """清单写入采用临时文件 + 原子替换；成功后无 .tmp 残留，JSON 始终有效。"""
    client, db, upload_dir = ctx
    entry_file = upload_dir / ".orphan_cleanup.json"
    entry_file.write_text(json.dumps([
        {"doc_id": "old", "path": "old.txt", "phase": fs._PHASE_CONFIRMED}
    ], ensure_ascii=False), encoding="utf-8")

    real_replace = os.replace
    calls = []

    def spy(src, dst):
        calls.append((src, dst))
        return real_replace(src, dst)

    monkeypatch.setattr(fs.os, "replace", spy)
    fs.register_cleanup_intent("new", "/uploads/new.txt")

    assert len(calls) == 1
    assert calls[0][0].endswith(".tmp")
    assert calls[0][1] == str(entry_file)
    assert not (upload_dir / ".orphan_cleanup.json.tmp").exists()
    data = json.loads(entry_file.read_text(encoding="utf-8"))
    assert {e["path"] for e in data} == {"old.txt", "new.txt"}


def test_failed_atomic_replace_keeps_previous_manifest_intact(ctx, monkeypatch):
    """原子替换失败时旧清单完整保留、.tmp 被清理，不留下半写入 JSON。"""
    client, db, upload_dir = ctx
    entry_file = upload_dir / ".orphan_cleanup.json"
    old = [{"doc_id": "old", "path": "old.txt", "phase": fs._PHASE_CONFIRMED}]
    entry_file.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    tmp_file = upload_dir / ".orphan_cleanup.json.tmp"

    def boom(src, dst):
        raise OSError("替换失败")

    monkeypatch.setattr(fs.os, "replace", boom)
    with pytest.raises(OSError):
        fs.register_cleanup_intent("new", "/uploads/new.txt")

    assert not tmp_file.exists()
    assert json.loads(entry_file.read_text(encoding="utf-8")) == old


def test_permanent_delete_removes_file_and_clears_manifest_entry(ctx):
    """正常彻底删除：物理文件与预登记条目都被清理，清单回归空。"""
    client, db, upload_dir = ctx
    target = upload_dir / "orphan_test_file.txt"
    target.write_text("x", encoding="utf-8")

    resp = client.delete("/api/v1/documents/doc_del/permanent", params={"user_id": "u_zhangsan"})
    assert resp.status_code == 200
    assert resp.json()["file_cleanup"] == "success"
    assert not target.exists()
    assert json.loads((upload_dir / ".orphan_cleanup.json").read_text(encoding="utf-8")) == []
