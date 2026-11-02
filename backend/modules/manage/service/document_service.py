from sqlalchemy.orm import Session

from modules.ingest.domain.models import Document
from modules.ingest.service.reindex_service import reindex_document


def update_document_meta(db: Session, doc_id: str, **kwargs):
    """更新文档元数据及内容"""

    doc = db.query(Document).filter(
        Document.id == doc_id
    ).first()

    if not doc:
        raise ValueError("文档不存在")

    # 只允许修改指定的元数据
    allowed_fields = {"title", "is_public"}
    content = kwargs.pop("content", None)

    unknown_fields = set(kwargs.keys()) - allowed_fields
    if unknown_fields:
        raise ValueError(f"不支持修改的字段：{unknown_fields}")

    try:
        # 修改文档标题
        if "title" in kwargs:
            title = kwargs["title"]

            if not title or not title.strip():
                raise ValueError("文档标题不能为空")

            doc.title = title.strip()

        # 修改公开状态
        if "is_public" in kwargs:
            doc.is_public = kwargs["is_public"]

        # 如果传入了正文，通知 ingest 重新索引
        if content is not None:
            reindex_document(db, doc_id, content)

        db.commit()
        db.refresh(doc)

        return doc

    except Exception:
        db.rollback()
        raise

def list_documents(db: Session, filters: dict | None = None):
    """根据筛选条件获取文档列表"""

    filters = filters or {}
    query = db.query(Document)

    # 按所有者筛选
    owner_id = filters.get("owner_id")
    if owner_id:
        query = query.filter(Document.owner_id == owner_id)

    # 按标题关键词筛选
    keyword = filters.get("keyword")
    if keyword and keyword.strip():
        query = query.filter(
            Document.title.like(f"%{keyword.strip()}%")
        )

    # 按文档类型筛选
    source_type = filters.get("source_type")
    if source_type:
        query = query.filter(Document.source_type == source_type)

    # 按公开状态筛选
    is_public = filters.get("is_public")
    if is_public is not None:
        query = query.filter(Document.is_public == is_public)

    documents = query.order_by(
        Document.created_at.desc()
    ).all()

    return [
        {
            "id": doc.id,
            "title": doc.title,
            "source_type": doc.source_type,
            "source_url": doc.source_url,
            "is_public": doc.is_public,
            "owner_id": doc.owner_id
        }
        for doc in documents
    ]