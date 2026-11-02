import uuid

from sqlalchemy.orm import Session

from modules.manage.domain.models import Tag, DocumentTag
from modules.ingest.domain.models import Document


def create_tag(db: Session, name: str):
    """创建标签"""
    name = name.strip()

    if not name:
        raise ValueError("标签名称不能为空")

    existing_tag = db.query(Tag).filter(Tag.name == name).first()

    if existing_tag:
        raise ValueError("标签已存在")

    tag = Tag(
        id=str(uuid.uuid4()),
        name=name,
        pinned=False
    )

    db.add(tag)
    db.commit()
    db.refresh(tag)

    return tag


def get_all_tags(db: Session):
    """获取所有标签"""
    return db.query(Tag).order_by(Tag.name.asc()).all()

def delete_tag(db: Session, tag_id: str):
    """删除标签"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()

    if not tag:
        raise ValueError("标签不存在")

    # 先删除标签与文档的关联
    db.query(DocumentTag).filter(
        DocumentTag.tag_id == tag_id
    ).delete(synchronize_session=False)

    db.delete(tag)
    db.commit()

    return {"message": "标签删除成功"}


def pin_tag(db: Session, tag_id: str):
    """切换标签置顶状态"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()

    if not tag:
        raise ValueError("标签不存在")

    tag.pinned = not tag.pinned

    db.commit()
    db.refresh(tag)

    return tag

def add_tag_to_doc(db: Session, doc_id: str, tag_id: str):
    """给文档添加标签"""
    document = db.query(Document).filter(
        Document.id == doc_id
    ).first()

    if not document:
        raise ValueError("文档不存在")

    tag = db.query(Tag).filter(Tag.id == tag_id).first()

    if not tag:
        raise ValueError("标签不存在")

    existing = db.query(DocumentTag).filter(
        DocumentTag.document_id == doc_id,
        DocumentTag.tag_id == tag_id
    ).first()

    if existing:
        raise ValueError("该文档已经拥有此标签")

    relation = DocumentTag(
        document_id=doc_id,
        tag_id=tag_id
    )

    db.add(relation)
    db.commit()

    return {"message": "标签添加成功"}


def remove_tag_from_doc(db: Session, doc_id: str, tag_id: str):
    """移除文档标签"""
    relation = db.query(DocumentTag).filter(
        DocumentTag.document_id == doc_id,
        DocumentTag.tag_id == tag_id
    ).first()

    if not relation:
        raise ValueError("文档标签关联不存在")

    db.delete(relation)
    db.commit()

    return {"message": "标签移除成功"}

def list_documents_by_tag(db: Session, tag_name: str):
    """根据标签名称查询文档"""
    tag = db.query(Tag).filter(
        Tag.name == tag_name
    ).first()

    if not tag:
        raise ValueError("标签不存在")

    documents = (
        db.query(Document)
        .join(
            DocumentTag,
            Document.id == DocumentTag.document_id
        )
        .filter(DocumentTag.tag_id == tag.id)
        .all()
    )

    return documents