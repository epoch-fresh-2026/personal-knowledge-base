import asyncio
import json

from modules.retrieve.service import search as search_service


def test_cosine_similarity():
    """测试余弦相似度计算。"""

    assert search_service.cosine_similarity(
        [1.0, 0.0],
        [1.0, 0.0]
    ) == 1.0

    assert search_service.cosine_similarity(
        [1.0, 0.0],
        [0.0, 1.0]
    ) == 0.0

    assert search_service.cosine_similarity(
        [1.0],
        [1.0, 2.0]
    ) == 0.0

    assert search_service.cosine_similarity(
        [0.0, 0.0],
        [1.0, 0.0]
    ) == 0.0


def test_tokenize():
    """测试中文查询分词和去重。"""

    keywords = search_service.tokenize(
        "个人知识库系统的知识库检索"
    )

    assert isinstance(keywords, list)
    assert "的" not in keywords
    assert len(keywords) == len(set(keywords))


def test_search_keyword_fallback(monkeypatch):
    """测试 Embedding 服务不可用时降级到关键词检索。"""

    chunk = type("FakeChunk", (), {
        "id": "chunk-001",
        "document_id": "doc-001",
        "content": "个人知识库支持关键词检索",
        "chunk_index": 0,
    })()

    monkeypatch.setattr(
        search_service.chunk_repo,
        "search_by_keywords",
        lambda db, keywords, top_k=5: [chunk]
    )

    async def fake_get_embedding(text):
        raise RuntimeError("Embedding API 不可用")

    monkeypatch.setattr(
        search_service,
        "get_embedding",
        fake_get_embedding
    )

    result = asyncio.run(
        search_service.search(
            db=None,
            query="个人知识库检索",
            top_k=5
        )
    )

    assert result["query"] == "个人知识库检索"
    assert len(result["results"]) == 1
    assert result["results"][0]["chunk_id"] == "chunk-001"
    assert result["results"][0]["semantic_score"] == 0.0
    assert result["results"][0]["retrieval_score"] > 0


def test_search_semantic_retrieval(monkeypatch):
    """测试语义检索能够找到关键词未命中的资料。"""

    chunk = type("FakeChunk", (), {
        "id": "chunk-002",
        "document_id": "doc-002",
        "content": "缓存系统通过频率统计管理数据",
        "chunk_index": 0,
        "embedding": json.dumps([1.0, 0.0]),
    })()

    monkeypatch.setattr(
        search_service.chunk_repo,
        "search_by_keywords",
        lambda db, keywords, top_k=5: []
    )

    async def fake_get_embedding(text):
        return [1.0, 0.0]

    monkeypatch.setattr(
        search_service,
        "get_embedding",
        fake_get_embedding
    )

    class FakeQuery:
        def filter(self, *args):
            return self

        def all(self):
            return [chunk]

    class FakeDB:
        def query(self, model):
            return FakeQuery()

    result = asyncio.run(
        search_service.search(
            db=FakeDB(),
            query="缓存如何管理数据",
            top_k=5
        )
    )

    assert len(result["results"]) == 1

    item = result["results"][0]

    assert item["chunk_id"] == "chunk-002"
    assert item["semantic_score"] == 1.0
    assert item["retrieval_score"] >= 0.7


def test_search_empty_query():
    """测试空查询。"""

    result = asyncio.run(
        search_service.search(
            db=None,
            query="   ",
            top_k=5
        )
    )

    assert result["keywords"] == []
    assert result["results"] == []


def test_semantic_search_excludes_soft_deleted_document(monkeypatch):
    """语义检索路径必须排除已软删除文档的 Chunk（Issue #47 规则 C）。

    使用真实内存 SQLite + relationship `has()` 过滤，不再使用
    ``filter()`` 无条件返回全部 Chunk 的 FakeDB，确保 search.py 中
    ``Chunk.document.has(Document.is_deleted == False)`` 真正执行。
    检索范围（owner/public）本 Issue 不引入，仍留待 #46。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from shared.db import Base
    from modules.ingest.domain.models import User, Document, Chunk

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()

    db.add(User(id="u_owner", nickname="所有者"))
    db.add(Document(id="doc_active", title="正常文档", source_type="text",
                    owner_id="u_owner", is_deleted=False, is_public=False))
    db.add(Document(id="doc_deleted", title="已删除文档", source_type="text",
                    owner_id="u_owner", is_deleted=True, is_public=True))
    db.add_all([
        Chunk(id="c_active", document_id="doc_active", content="知识库内容甲",
              embedding=json.dumps([1.0, 0.0]), chunk_index=0),
        Chunk(id="c_deleted", document_id="doc_deleted", content="知识库内容乙",
              embedding=json.dumps([1.0, 0.0]), chunk_index=0),
    ])
    db.commit()

    # 关键词路径置空，让结果只能来自语义路径，从而精确验证语义分支的软删除过滤。
    monkeypatch.setattr(
        search_service.chunk_repo,
        "search_by_keywords",
        lambda db, keywords, top_k=5: [],
    )

    async def fake_get_embedding(text):
        return [1.0, 0.0]

    monkeypatch.setattr(search_service, "get_embedding", fake_get_embedding)

    result = asyncio.run(
        search_service.search(db, "知识库检索", top_k=10)
    )

    chunk_ids = {item["chunk_id"] for item in result["results"]}
    doc_ids = {item["document_id"] for item in result["results"]}
    # 正常文档的 Chunk 可被语义检索到
    assert "c_active" in chunk_ids
    assert "doc_active" in doc_ids
    # 软删除文档的 Chunk 必须被 has(is_deleted == False) 过滤掉
    assert "c_deleted" not in chunk_ids
    assert "doc_deleted" not in doc_ids
    db.close()