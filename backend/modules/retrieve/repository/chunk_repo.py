from sqlalchemy.orm import Session

from modules.ingest.domain.models import Chunk, Document


def search_by_keywords(db: Session, keywords: list[str], top_k: int = 5) -> list[Chunk]:
    """
    关键词检索：对每个关键词做 LIKE 匹配，去重后返回。
    简单版：不考虑相关度排序（用 Python 再算）。

    已删除文档（Issue #47 规则 C）的 chunks 不参与检索。
    """
    if not keywords:
        return []

    from sqlalchemy import or_
    conditions = [Chunk.content.like(f"%{kw}%") for kw in keywords]
    chunks = (
        db.query(Chunk)
        .filter(
            Chunk.document.has(Document.is_deleted == False),
            or_(*conditions),
        )
        .all()
    )

    # Python 里算命中数排序
    def hit_count(chunk: Chunk) -> int:
        return sum(1 for kw in keywords if kw in chunk.content)

    chunks.sort(key=hit_count, reverse=True)
    return chunks[:top_k]
