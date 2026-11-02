import uuid

from sqlalchemy.orm import Session

from modules.ingest.domain.models import Document, Chunk
from modules.ingest.service.splitter import split_markdown


def reindex_document(db: Session, doc_id: str, content: str):
    """重新拆分文档内容，并替换原有 chunks"""

    doc = db.query(Document).filter(
        Document.id == doc_id
    ).first()

    if not doc:
        raise ValueError("文档不存在")

    if not content or not content.strip():
        raise ValueError("文档内容不能为空")

    # 重新拆分文档
    chunks_text = split_markdown(content)

    # 删除旧的 chunks
    db.query(Chunk).filter(
        Chunk.document_id == doc_id
    ).delete(synchronize_session=False)

    # 创建新的 chunks
    new_chunks = [
        Chunk(
            id=str(uuid.uuid4()),
            document_id=doc_id,
            content=text,
            embedding=None,
            chunk_index=i
        )
        for i, text in enumerate(chunks_text)
    ]

    db.add_all(new_chunks)
    db.flush()

    return doc