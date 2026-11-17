from datetime import datetime

from sqlalchemy.orm import Session

from modules.ingest.domain.models import Document, Chunk


def save_document(db: Session, doc: Document, chunks: list[Chunk]) -> Document:
    """保存文档及其 chunks"""
    db.add(doc)
    for chunk in chunks:
        db.add(chunk)
    db.commit()
    db.refresh(doc)
    return doc


def get_document(db: Session, doc_id: str) -> Document | None:
    """获取未删除的文档（Issue #47）。"""
    return db.query(Document).filter(
        Document.id == doc_id,
        Document.is_deleted == False,
    ).first()


def list_documents(db: Session, limit: int = 50) -> list[Document]:
    """列出未删除的文档（Issue #47）。"""
    return (
        db.query(Document)
        .filter(Document.is_deleted == False)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .all()
    )


def delete_document(db: Session, doc_id: str) -> bool:
    """
    软删除文档（Issue #47 规则 C）。

    不再执行物理删除；所有权校验由上层 service 负责。
    """
    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.is_deleted == False,
    ).first()
    if not doc:
        return False
    doc.is_deleted = True
    doc.deleted_at = datetime.utcnow()
    db.commit()
    return True
