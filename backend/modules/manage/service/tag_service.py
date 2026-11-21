import uuid

from sqlalchemy.orm import Session

from modules.manage.domain.models import Tag, DocumentTag
from modules.ingest.domain.models import Document

# C2 整改：标签关联文档查询的可见性口径直接复用 shared 单一定义，
# 与检索、正文读取、收藏保持一致，避免多入口各自实现出不同版本。
from shared.document_visibility import visible_document_condition


def _normalize_name(name: str) -> str:
    """标签名称规范化：去首尾空白 + 统一大小写（casefold），用于唯一性比较。"""
    return (name or "").strip().casefold()


def create_tag(db: Session, name: str, user_id: str):
    """创建全局共享标签（Issue #51 规则 B）。

    名称非空、规范化后全局唯一；记录创建者。所有用户可使用已有标签，
    但只有创建者日后可删除。
    """
    name = (name or "").strip()

    if not name:
        raise ValueError("标签名称不能为空")

    normalized = _normalize_name(name)
    # 规范化后全局唯一：在 Python 层比较，兼容大小写/空白差异
    existing = [
        t for t in db.query(Tag).all()
        if _normalize_name(t.name) == normalized
    ]
    if existing:
        raise ValueError("标签已存在")

    tag = Tag(
        id=str(uuid.uuid4()),
        name=name,
        pinned=False,
        creator_id=user_id,
    )

    db.add(tag)
    db.commit()
    db.refresh(tag)

    return tag


def get_all_tags(db: Session):
    """获取所有全局共享标签（置顶为全局状态，所有用户结果一致）。"""
    return db.query(Tag).order_by(Tag.pinned.desc(), Tag.name.asc()).all()


def delete_tag(db: Session, tag_id: str, user_id: str):
    """删除标签（Issue #51 原文规则）：仅创建者可删除；仍有关联时禁止删除。

    全局共享标签：创建者可删除标签，但删除前必须确认没有文档仍在使用它；
    仍有关联则拒绝并提示先解除关联，不静默删除任何文档关联。
    非创建者（含历史 creator_id 为 NULL 的标签）一律拒绝，且不改动任何数据。
    """
    tag = db.query(Tag).filter(Tag.id == tag_id).first()

    if not tag:
        raise ValueError("标签不存在")

    if tag.creator_id is None or tag.creator_id != user_id:
        raise ValueError("只有标签创建者可以删除标签")

    in_use = db.query(DocumentTag).filter(
        DocumentTag.tag_id == tag_id
    ).first()
    if in_use:
        raise ValueError("标签仍有关联文档，请先解除关联后再删除")

    db.delete(tag)
    db.commit()

    return {"message": "标签删除成功"}


def pin_tag(db: Session, tag_id: str):
    """切换标签置顶状态：修改全局状态，所有用户看到一致结果。"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()

    if not tag:
        raise ValueError("标签不存在")

    tag.pinned = not tag.pinned

    db.commit()
    db.refresh(tag)

    return tag


def add_tag_to_doc(db: Session, doc_id: str, tag_id: str, user_id: str):
    """给文档添加标签（Issue #51）：校验当前用户对文档的管理权限（文档所有者）。"""
    document = db.query(Document).filter(
        Document.id == doc_id,
        Document.is_deleted == False,
    ).first()

    if not document:
        raise ValueError("文档不存在")

    if document.owner_id != user_id:
        raise ValueError("无权管理该文档")

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


def remove_tag_from_doc(db: Session, doc_id: str, tag_id: str, user_id: str):
    """移除文档标签（Issue #51）：校验当前用户对文档的管理权限。"""
    document = db.query(Document).filter(
        Document.id == doc_id,
        Document.is_deleted == False,
    ).first()

    if not document:
        raise ValueError("文档不存在")

    if document.owner_id != user_id:
        raise ValueError("无权管理该文档")

    relation = db.query(DocumentTag).filter(
        DocumentTag.document_id == doc_id,
        DocumentTag.tag_id == tag_id
    ).first()

    if not relation:
        raise ValueError("文档标签关联不存在")

    db.delete(relation)
    db.commit()

    return {"message": "标签移除成功"}


def list_documents_by_tag(db: Session, tag_name: str, user_id: str):
    """根据标签名称查询文档（Issue #51）。

    只返回当前用户可访问的文档：自己拥有的文档，或已公开的文档；
    并排除已软删除文档。标签是全局的，但文档可见范围按当前用户过滤。
    """
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
        .filter(
            DocumentTag.tag_id == tag.id,
            # 复用 shared 单一定义的可见性条件（未删除 且 [本人 或 已公开]），
            # 与检索/正文/收藏同一口径；含 fail-closed 的 user_id 校验。
            visible_document_condition(user_id),
        )
        .all()
    )

    return documents
