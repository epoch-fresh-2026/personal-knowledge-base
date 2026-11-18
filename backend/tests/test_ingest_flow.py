"""Issue #52：统一收录流程（解析→切分→Embedding→单事务保存→失败补偿）验收测试。

覆盖验收标准与用户裁决的 20 项场景：
- 文件上传：成功、解析失败、文本空内容、图片/视频占位、切分失败、
  Embedding 首/后续 chunk 失败、DB 提交失败、转正式文件失败、
  各失败场景 DB 无残留、临时文件清理、成功后正式文件与 source_url 正确；
- URL 收录：合法 URL 成功、非法 URL 请求前拒绝、抓取失败、正文为空、
  Embedding 失败、原始 source_url、失败无残留；
- 共享 Embedding：收录与检索使用同一 get_embedding，无第二套供应商实现。

所有文件 IO 指向 tmp_path，Embedding 与 httpx 均被 mock，不触碰真实数据库、
真实 uploads 与真实网络。
"""

import asyncio
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.db import Base, get_db
from modules.ingest.domain.models import User, Document, Chunk
from api.router import api_router
from modules.ingest.service import ingest_service
from modules.ingest.service import embedding_service as emb_mod
from modules.retrieve.service import search as search_mod
from shared import embedding as shared_embedding


# ---------- fixture ----------

@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """内存库 + 客户端 + 隔离的上传/临时目录；Embedding 默认返回 1024 维。"""
    upload_dir = tmp_path / "uploads"
    temp_dir = tmp_path / ".ingest_tmp"
    monkeypatch.setattr(ingest_service, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(ingest_service, "TEMP_DIR", str(temp_dir))

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    db.add(User(id="u_zhangsan", nickname="张三"))
    db.commit()

    def fake_embeddings(chunks):
        for chunk in chunks:
            chunk.embedding = "[0.1]"  # 维度/内容不重要，测试不涉及真实检索
        return None

    async def async_fake(chunks):
        fake_embeddings(chunks)

    monkeypatch.setattr(ingest_service, "generate_chunk_embeddings", async_fake)

    def override_get_db():
        yield db

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c, db, upload_dir, temp_dir

    db.close()
    engine.dispose()


def _dirs_empty(*dirs):
    for d in dirs:
        if d.exists():
            assert list(d.iterdir()) == [], f"{d} 应为空，实际有残留"


def _no_docs(db):
    assert db.query(Document).count() == 0
    assert db.query(Chunk).count() == 0


def _upload(client, filename, content, is_public=True):
    return client.post(
        "/api/v1/documents/upload",
        params={"user_id": "u_zhangsan", "is_public": str(is_public).lower()},
        files={"file": (filename, content, "application/octet-stream")},
    )


# ---------- 文件上传：成功路径 ----------

def test_upload_text_success(ctx):
    client, db, upload_dir, temp_dir = ctx
    resp = _upload(client, "note.md", "# 标题\n\n内容段落".encode("utf-8"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["chunks_count"] >= 1

    doc = db.query(Document).first()
    assert doc is not None
    assert doc.owner_id == "u_zhangsan"
    assert doc.source_url.startswith("/uploads/")
    # 正式文件存在，源文件名保留在路径中
    formal_name = doc.source_url[len("/uploads/"):]
    assert (upload_dir / formal_name).exists()
    _dirs_empty(temp_dir)


def test_upload_image_placeholder_success(ctx):
    client, db, upload_dir, temp_dir = ctx
    resp = _upload(client, "pic.png", b"\x89PNG\r\n\x1a\nfake")
    assert resp.status_code == 200, resp.text
    doc = db.query(Document).first()
    assert doc.source_type == "image"
    chunk = db.query(Chunk).first()
    assert "图片文件" in chunk.content  # 占位文本，非解析失败
    assert (upload_dir / doc.source_url[len("/uploads/"):]).exists()


def test_upload_video_placeholder_success(ctx):
    client, db, upload_dir, temp_dir = ctx
    resp = _upload(client, "clip.mp4", b"fake video bytes")
    assert resp.status_code == 200, resp.text
    doc = db.query(Document).first()
    assert doc.source_type == "video"
    chunk = db.query(Chunk).first()
    assert "视频文件" in chunk.content
    _dirs_empty(temp_dir)


# ---------- 文件名路径穿越防护 ----------

@pytest.mark.parametrize("evil_name", [
    "../../escape.md",
    "..\\escape.txt",
    "nested/evil.md",
    "C:\\evil\\note.md",
])
def test_upload_traversal_filename_is_sanitized_inside_dirs(ctx, evil_name):
    """目录成分被剥离；文件仍落在临时/正式目录内，标题保留原始文件名。"""
    client, db, upload_dir, temp_dir = ctx
    base = evil_name.replace("\\", "/").rsplit("/", 1)[-1]
    resp = _upload(client, evil_name, "# 标题\n\n正文内容".encode("utf-8"))
    assert resp.status_code == 200, resp.text

    doc = db.query(Document).first()
    assert doc is not None
    # 服务仍按收到的文件名设置标题；multipart 框架可能先剥离盘符路径。
    assert doc.title in {evil_name, base}

    stored_name = doc.source_url[len("/uploads/"):]
    assert "/" not in stored_name and "\\" not in stored_name
    assert ".." not in stored_name
    assert (upload_dir / stored_name).exists()
    _dirs_empty(temp_dir)

    assert not (upload_dir.parent / base).exists(), "不得在正式目录之外留下文件"


@pytest.mark.parametrize("bad_name", ["..", ".", "   "])
def test_upload_dot_or_blank_filename_rejected(ctx, bad_name):
    client, db, upload_dir, temp_dir = ctx
    resp = _upload(client, bad_name, b"content")
    assert resp.status_code == 400
    assert "文件名" in resp.json()["detail"]
    _no_docs(db)
    _dirs_empty(upload_dir, temp_dir)


def test_inside_directory_rejects_traversal_for_both_roots(ctx):
    """防御纵深：即便上游返回越界名称，两条目标路径也必须被拒绝。"""
    client, db, upload_dir, temp_dir = ctx
    for root in (str(temp_dir), str(upload_dir)):
        with pytest.raises(ingest_service.IngestError, match="越界"):
            ingest_service._inside_directory(root, "../evil.md")


def test_safe_upload_name_rejects_nul_character():
    """纯函数校验：NUL 文件名直接拒绝，不访问数据库或上传目录。"""
    with pytest.raises(ingest_service.IngestError, match="文件名"):
        ingest_service._safe_upload_name("a\x00b.md")


def test_inside_directory_rejects_symlink_escape(tmp_path):
    """根目录内符号链接指向外部文件时，realpath 校验必须拒绝。"""
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("外部目标文件", encoding="utf-8")

    symlink_name = "escape.md"
    link = root_dir / symlink_name
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"当前环境不支持创建符号链接：{e}")

    with pytest.raises(ingest_service.IngestError, match="越界"):
        ingest_service._inside_directory(str(root_dir), symlink_name)


# ---------- 文件上传：失败路径 ----------

def test_upload_pdf_parse_failure_cleans_all(ctx, monkeypatch):
    client, db, upload_dir, temp_dir = ctx
    monkeypatch.setattr(
        ingest_service, "_parse_uploaded_file",
        lambda p, f: (_ for _ in ()).throw(Exception("损坏的 PDF")),
    )
    resp = _upload(client, "broken.pdf", b"not a pdf")
    assert resp.status_code == 400
    assert "解析失败" in resp.json()["detail"]
    _no_docs(db)
    _dirs_empty(upload_dir, temp_dir)


def test_upload_docx_parse_failure_cleans_all(ctx, monkeypatch):
    client, db, upload_dir, temp_dir = ctx
    monkeypatch.setattr(
        ingest_service, "_parse_uploaded_file",
        lambda p, f: (_ for _ in ()).throw(Exception("损坏的 DOCX")),
    )
    resp = _upload(client, "broken.docx", b"not a docx")
    assert resp.status_code == 400
    assert "解析失败" in resp.json()["detail"]
    _no_docs(db)
    _dirs_empty(upload_dir, temp_dir)


def test_upload_text_empty_content_rejected(ctx):
    client, db, upload_dir, temp_dir = ctx
    resp = _upload(client, "empty.txt", b"   \n\n  ")
    assert resp.status_code == 400
    assert "为空" in resp.json()["detail"]
    _no_docs(db)
    _dirs_empty(upload_dir, temp_dir)


def test_upload_split_failure_cleans_all(ctx, monkeypatch):
    client, db, upload_dir, temp_dir = ctx
    monkeypatch.setattr(
        ingest_service, "split_markdown",
        lambda content: (_ for _ in ()).throw(Exception("切分异常")),
    )
    resp = _upload(client, "note.md", b"valid content")
    assert resp.status_code == 500
    assert "切分失败" in resp.json()["detail"]
    _no_docs(db)
    _dirs_empty(upload_dir, temp_dir)


def test_upload_embedding_first_chunk_failure_cleans_all(ctx, monkeypatch):
    """使用真实批量适配器，仅让第 1 个 chunk 的共享 Embedding 调用失败。"""
    client, db, upload_dir, temp_dir = ctx
    # 恢复真实批量适配器（fixture 默认是快速 fake）
    monkeypatch.setattr(
        ingest_service,
        "generate_chunk_embeddings",
        emb_mod.generate_chunk_embeddings,
    )
    monkeypatch.setattr(
        ingest_service, "split_markdown",
        lambda content: ["段落一", "段落二", "段落三"],
    )
    calls = {"n": 0}

    async def fail_first(text):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("第 1 个 chunk 向量化失败")
        return [0.1] * 1024

    # 批量适配器内部调用的是其模块导入的 get_embedding
    monkeypatch.setattr(emb_mod, "get_embedding", fail_first)
    resp = _upload(client, "note.md", b"any content")
    assert resp.status_code == 500
    assert "Embedding" in resp.json()["detail"]
    assert calls["n"] == 1  # 首个 chunk 失败后立即终止，不再调用后续
    _no_docs(db)
    _dirs_empty(upload_dir, temp_dir)


def test_upload_embedding_later_chunk_failure_cleans_all(ctx, monkeypatch):
    """使用真实批量适配器，让第 2 个 chunk 失败，验证整体回滚。"""
    client, db, upload_dir, temp_dir = ctx
    monkeypatch.setattr(
        ingest_service,
        "generate_chunk_embeddings",
        emb_mod.generate_chunk_embeddings,
    )
    # 固定切出 3 个 chunk，确保能测到"后续 chunk 失败"
    monkeypatch.setattr(
        ingest_service, "split_markdown",
        lambda content: ["段落一", "段落二", "段落三"],
    )
    calls = {"n": 0}

    async def fail_second(text):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("第 2 个 chunk 向量化失败")
        return [0.1] * 1024

    monkeypatch.setattr(emb_mod, "get_embedding", fail_second)
    resp = _upload(client, "note.md", b"any content")
    assert resp.status_code == 500
    assert "Embedding" in resp.json()["detail"]
    assert calls["n"] == 2  # 第 1 个成功、第 2 个失败后终止
    _no_docs(db)
    _dirs_empty(upload_dir, temp_dir)


def test_upload_db_commit_failure_cleans_formal_file(ctx, monkeypatch):
    client, db, upload_dir, temp_dir = ctx

    def boom(db, doc, chunks):
        raise RuntimeError("数据库磁盘已满")

    monkeypatch.setattr(ingest_service, "save_document", boom)
    resp = _upload(client, "note.md", b"valid content")
    assert resp.status_code == 500
    assert "保存失败" in resp.json()["detail"]
    _no_docs(db)
    # 关键：文件已移动到正式目录后 DB 失败，正式文件也必须被补偿删除
    _dirs_empty(upload_dir, temp_dir)


def test_upload_move_to_formal_failure_cleans_temp(ctx, monkeypatch):
    client, db, upload_dir, temp_dir = ctx

    def boom_move(src, dst):
        raise OSError("目标目录不可写")

    monkeypatch.setattr(ingest_service.shutil, "move", boom_move)
    resp = _upload(client, "note.md", b"valid content")
    assert resp.status_code == 500
    assert "正式文件保存失败" in resp.json()["detail"]
    _no_docs(db)
    _dirs_empty(upload_dir, temp_dir)


# ---------- URL 收录 ----------

def _ingest_url(client, url, is_public=True):
    return client.post(
        "/api/v1/documents/url",
        params={"user_id": "u_zhangsan"},
        json={"url": url, "is_public": is_public},
    )


def test_url_success_saves_original_source_url(ctx, monkeypatch):
    client, db, upload_dir, temp_dir = ctx
    calls = {"n": 0}

    class FakeResp:
        text = "<html><body><p>网页正文内容</p><p>第二段内容</p></body></html>"

        def raise_for_status(self):
            pass

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, url, timeout):
            calls["n"] += 1
            assert url == "https://example.com/page?a=1"
            return FakeResp()

    monkeypatch.setattr(ingest_service.httpx, "AsyncClient", FakeClient)
    resp = _ingest_url(client, "https://example.com/page?a=1")
    assert resp.status_code == 200, resp.text
    assert calls["n"] == 1
    doc = db.query(Document).first()
    # 原始 URL（含查询串），不是重定向或本地路径
    assert doc.source_url == "https://example.com/page?a=1"
    assert doc.source_type == "url"
    assert doc.owner_id == "u_zhangsan"


@pytest.mark.parametrize("bad_url", [
    "not a url",
    "ftp://example.com/x",
    "http://",
    "/uploads/local.md",
    "",
])
def test_url_invalid_rejected_before_network(ctx, monkeypatch, bad_url):
    client, db, upload_dir, temp_dir = ctx
    calls = {"n": 0}

    class ShouldNotCall:
        async def __aenter__(self):
            calls["n"] += 1
            return self

        async def __aexit__(self, *a):
            pass

    monkeypatch.setattr(ingest_service.httpx, "AsyncClient", ShouldNotCall)
    resp = _ingest_url(client, bad_url)
    assert resp.status_code == 400
    assert "URL" in resp.json()["detail"]
    assert calls["n"] == 0, "非法 URL 不得发起网络请求"
    _no_docs(db)


def test_url_fetch_failure_no_residue(ctx, monkeypatch):
    client, db, upload_dir, temp_dir = ctx

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, url, timeout):
            raise RuntimeError("连接超时")

    monkeypatch.setattr(ingest_service.httpx, "AsyncClient", FakeClient)
    resp = _ingest_url(client, "https://example.com/x")
    assert resp.status_code == 400
    assert "抓取失败" in resp.json()["detail"]
    _no_docs(db)


def test_url_empty_content_rejected(ctx, monkeypatch):
    client, db, upload_dir, temp_dir = ctx

    class FakeResp:
        text = "<html><body>   </body></html>"

        def raise_for_status(self):
            pass

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, url, timeout):
            return FakeResp()

    monkeypatch.setattr(ingest_service.httpx, "AsyncClient", FakeClient)
    resp = _ingest_url(client, "https://example.com/empty")
    assert resp.status_code == 400
    assert "为空" in resp.json()["detail"]
    _no_docs(db)


def test_url_embedding_failure_no_residue(ctx, monkeypatch):
    client, db, upload_dir, temp_dir = ctx

    class FakeResp:
        text = "<html><body><p>正文内容</p></body></html>"

        def raise_for_status(self):
            pass

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, url, timeout):
            return FakeResp()

    monkeypatch.setattr(ingest_service.httpx, "AsyncClient", FakeClient)

    async def boom(chunks):
        raise RuntimeError("向量化失败")

    monkeypatch.setattr(ingest_service, "generate_chunk_embeddings", boom)
    resp = _ingest_url(client, "https://example.com/x")
    assert resp.status_code == 500
    assert "Embedding" in resp.json()["detail"]
    _no_docs(db)


def test_url_db_failure_no_residue(ctx, monkeypatch):
    client, db, upload_dir, temp_dir = ctx

    class FakeResp:
        text = "<html><body><p>正文内容</p></body></html>"

        def raise_for_status(self):
            pass

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, url, timeout):
            return FakeResp()

    monkeypatch.setattr(ingest_service.httpx, "AsyncClient", FakeClient)

    def boom(db, doc, chunks):
        raise RuntimeError("数据库错误")

    monkeypatch.setattr(ingest_service, "save_document", boom)
    resp = _ingest_url(client, "https://example.com/x")
    assert resp.status_code == 500
    _no_docs(db)


# ---------- 清理失败留痕（#52 补充修正） ----------

def test_temp_file_cleanup_failure_is_logged_without_masking_original(ctx, monkeypatch, caplog):
    """临时文件清理失败：记录路径/阶段/原因，且不覆盖原始收录异常。"""
    client, db, upload_dir, temp_dir = ctx
    real_remove = ingest_service.os.remove

    def fail_temp_remove(path):
        if str(path).startswith(str(temp_dir)):
            raise OSError("临时目录只读")
        return real_remove(path)

    monkeypatch.setattr(ingest_service.os, "remove", fail_temp_remove)
    # 让收录在早期（解析）失败，触发 finally 的临时文件清理分支
    monkeypatch.setattr(
        ingest_service, "_parse_uploaded_file",
        lambda p, f: (_ for _ in ()).throw(Exception("损坏的 PDF")),
    )

    with caplog.at_level(logging.ERROR):
        resp = _upload(client, "broken.pdf", b"not a pdf")

    # 原始异常未被清理异常覆盖
    assert resp.status_code == 400
    assert "解析失败" in resp.json()["detail"]
    assert "临时目录只读" not in resp.json()["detail"]
    _no_docs(db)

    # 清理失败信息已记录：路径 + 阶段 + 原因
    assert "收录文件清理失败" in caplog.text
    assert str(temp_dir) in caplog.text
    assert "临时文件清理" in caplog.text
    assert "临时目录只读" in caplog.text


def test_formal_file_cleanup_failure_is_logged_without_masking_original(ctx, monkeypatch, caplog):
    """正式文件补偿清理失败：记录路径/阶段/原因，且不覆盖原始 DB 异常。"""
    client, db, upload_dir, temp_dir = ctx

    def boom(db, doc, chunks):
        raise RuntimeError("数据库磁盘已满")

    monkeypatch.setattr(ingest_service, "save_document", boom)
    real_remove = ingest_service.os.remove

    def fail_formal_remove(path):
        if str(path).startswith(str(upload_dir)):
            raise OSError("正式目录只读")
        return real_remove(path)

    monkeypatch.setattr(ingest_service.os, "remove", fail_formal_remove)

    with caplog.at_level(logging.ERROR):
        resp = _upload(client, "note.md", b"valid content")

    assert resp.status_code == 500
    assert "保存失败" in resp.json()["detail"]
    assert "正式目录只读" not in resp.json()["detail"]
    _no_docs(db)

    assert "收录文件清理失败" in caplog.text
    assert str(upload_dir) in caplog.text
    assert "正式文件补偿清理" in caplog.text
    assert "正式目录只读" in caplog.text
    # 文件已移动，临时路径已消失，不应产生"临时文件清理"误报
    assert "临时文件清理" not in caplog.text


def test_successful_ingest_never_invokes_cleanup(ctx, monkeypatch, caplog):
    """收录成功时不做任何清理，即使清理函数会失败也不改变成功结果（规则 5）。"""
    client, db, upload_dir, temp_dir = ctx
    calls = {"n": 0}

    def unexpected_remove(path):
        calls["n"] += 1
        raise OSError("成功路径不应触发清理")

    monkeypatch.setattr(ingest_service.os, "remove", unexpected_remove)

    with caplog.at_level(logging.ERROR):
        resp = _upload(client, "note.md", b"valid content")

    assert resp.status_code == 200, resp.text
    assert calls["n"] == 0, "成功收录不应调用任何文件清理"
    assert "收录文件清理失败" not in caplog.text
    doc = db.query(Document).first()
    assert doc is not None
    assert (upload_dir / doc.source_url[len("/uploads/"):]).exists()


# ---------- 共享 Embedding 唯一性 ----------

def test_shared_embedding_is_single_implementation():
    """收录适配器与检索服务都持有同一个 shared.embedding.get_embedding 函数对象。"""
    assert emb_mod.get_embedding is shared_embedding.get_embedding
    assert search_mod.get_embedding is shared_embedding.get_embedding


def test_no_duplicate_vendor_request_implementation():
    """项目中只有 shared/embedding.py 实现供应商 Embedding 请求URL。"""
    import os
    import pathlib

    backend_root = pathlib.Path(__file__).resolve().parents[1]
    marker = "embeddings/text-embedding/text-embedding"
    hits = []
    for root, dirs, files in os.walk(backend_root):
        # 只扫描生产代码目录；tests 内会出现该字符串用于断言，不算实现
        dirs[:] = [
            d for d in dirs
            if d not in (".venv", "__pycache__", "tests")
        ]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            with open(p, encoding="utf-8-sig") as f:
                if marker in f.read():
                    hits.append(os.path.relpath(p, backend_root))
    assert hits == ["shared\\embedding.py"] or hits == ["shared/embedding.py"], hits
