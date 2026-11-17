"""文件夹与资料管理服务（Issue #54 工程整理）。

文档删除生命周期（软删除/恢复/永久删除及孤立文件补偿）已于 Issue #54
迁入 modules.manage.service.document_service，本模块专注文件夹、公开资料与收藏。
"""

from sqlalchemy.orm import Session
from sqlalchemy import select
from modules.manage.domain.models import (
    Folder,
    DocumentFolder,
    FavoriteFolder,
    DocumentTag,
    Tag,
)
from modules.ingest.domain.models import Document, User, FavoriteDocument
from uuid import uuid4

# Issue #54：复用文档服务中统一的可见性口径（#49 收藏与 #50 正文同一规则）。
# document_service 不反向依赖本模块，无循环导入。
from modules.manage.service.document_service import (
    is_document_visible_to_user,
    visible_document_condition,
)


def _serialize_document(db: Session, doc: Document):
    """统一构建文档信息，并附带标签列表。"""
    tags = (
        db.query(Tag)
        .join(DocumentTag, Tag.id == DocumentTag.tag_id)
        .filter(DocumentTag.document_id == doc.id)
        .order_by(Tag.name)
        .all()
    )

    return {
        "id": doc.id,
        "title": doc.title,
        "source_type": doc.source_type,
        "source_url": doc.source_url,
        "is_public": doc.is_public,
        "owner_id": doc.owner_id,
        "tags": [
            {
                "id": tag.id,
                "name": tag.name,
                "pinned": tag.pinned,
            }
            for tag in tags
        ],
    }


def create_folder(db: Session, name: str, owner_id: str):
    folder = Folder(id=str(uuid4()), name=name, owner_id=owner_id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def get_all_folders(db: Session, user_id: str):
    folders = db.query(Folder).filter(Folder.owner_id == user_id).all()
    return [
        {"id": f.id, "name": f.name, "is_public": f.is_public}
        for f in folders
    ]


def add_doc_to_folder(db: Session, doc_id: str, folder_id: str, user_id: str):
    """
    添加文档到文件夹（Issue #48）：文件夹与文档均须归属当前用户。

    「有权管理的文档」按严格口径：仅当前用户拥有、且未软删除的文档；
    他人公开文档不等于可管理，不得加入自己的文件夹。只建立关联，
    不改变文档归属、公开状态，也不触碰文档本身。
    """
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.owner_id == user_id,
    ).first()
    if not folder:
        return {"error": "文件夹不存在或无权操作"}

    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.owner_id == user_id,
        Document.is_deleted == False,
    ).first()
    if not doc:
        return {"error": "文档不存在或无权操作"}

    exists = db.query(DocumentFolder).filter_by(
        document_id=doc_id,
        folder_id=folder_id,
    ).first()
    if not exists:
        df = DocumentFolder(document_id=doc_id, folder_id=folder_id)
        db.add(df)
        db.commit()

    return {"status": "success"}


def remove_doc_from_folder(db: Session, doc_id: str, folder_id: str, user_id: str):
    """
    从文件夹移除文档（Issue #48）：同时校验文件夹与文档的归属；
    只删除关联关系，不删除文档本身。允许清理已软删除文档的关联。
    """
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.owner_id == user_id,
    ).first()
    if not folder:
        return {"error": "文件夹不存在或无权操作"}

    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.owner_id == user_id,
    ).first()
    if not doc:
        return {"error": "文档不存在或无权操作"}

    df = db.query(DocumentFolder).filter_by(
        document_id=doc_id,
        folder_id=folder_id,
    ).first()

    if df:
        db.delete(df)
        db.commit()

    return {"status": "success"}


def get_documents_in_folder(db: Session, folder_id: str, user_id: str):
    """
    文件夹详情（Issue #48）：
    - 所有者：可见其中全部未软删除文档（含自身私有文档）；
    - 非所有者：仅当文件夹公开时可见其中未软删除、且自身公开的文档；
    - 私有文件夹对非所有者返回明确错误，杜绝通过 folder_id 直连读取。
    """
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        return {"error": "文件夹不存在"}

    is_owner = folder.owner_id == user_id
    if not is_owner and not folder.is_public:
        return {"error": "文件夹不存在或无权访问"}

    query = (
        db.query(Document)
        .join(
            DocumentFolder,
            Document.id == DocumentFolder.document_id,
        )
        .filter(
            DocumentFolder.folder_id == folder_id,
            Document.is_deleted == False,
        )
    )
    if not is_owner:
        query = query.filter(Document.is_public == True)

    return [_serialize_document(db, doc) for doc in query.all()]


def get_all_documents(db: Session, user_id: str):
    docs = (
        db.query(Document)
        .filter(
            Document.owner_id == user_id,
            Document.is_deleted == False,
        )
        .order_by(Document.created_at.desc())
        .all()
    )

    return [_serialize_document(db, doc) for doc in docs]


def get_uncategorized_documents(db: Session, user_id: str):
    subquery = db.query(DocumentFolder.document_id)

    docs = (
        db.query(Document)
        .filter(
            ~Document.id.in_(subquery),
            Document.owner_id == user_id,
            Document.is_deleted == False,
        )
        .order_by(Document.created_at.desc())
        .all()
    )

    return [_serialize_document(db, doc) for doc in docs]


def get_public_documents(
    db: Session,
    keyword: str = "",
    user_id: str = "",
):
    public_folder_ids = (
        db.query(Folder.id)
        .filter(Folder.is_public == True)
        .subquery()
    )

    doc_ids_in_public_folders = (
        db.query(DocumentFolder.document_id)
        .filter(
            DocumentFolder.folder_id.in_(select(public_folder_ids))
        )
        .subquery()
    )

    query = db.query(Document).filter(
        Document.is_public == True,
        Document.is_deleted == False,
        ~Document.id.in_(doc_ids_in_public_folders),
    )

    if keyword:
        query = (
            query.join(User, Document.owner_id == User.id, isouter=True)
            .filter(
                (Document.title.like(f"%{keyword}%"))
                | (User.nickname.like(f"%{keyword}%"))
            )
        )

    docs = query.all()

    fav_doc_ids = (
        [
            f.document_id
            for f in db.query(FavoriteDocument)
            .filter(FavoriteDocument.user_id == user_id)
            .all()
        ]
        if user_id
        else []
    )

    return [
        {
            "id": d.id,
            "title": d.title,
            "source_type": d.source_type,
            "source_url": d.source_url,
            "author_name": d.owner.nickname if d.owner else "未知",
            "author_avatar": d.owner.avatar if d.owner else "👤",
            "author_id": d.owner_id if d.owner_id else "unknown",
            "is_favorited": d.id in fav_doc_ids,
        }
        for d in docs
    ]


def get_user_public_docs(db: Session, user_id: str):
    docs = (
        db.query(Document)
        .filter(
            Document.is_public == True,
            Document.is_deleted == False,
            Document.owner_id == user_id,
        )
        .all()
    )

    return [
        {
            "id": d.id,
            "title": d.title,
            "source_type": d.source_type,
        }
        for d in docs
    ]


def toggle_doc_visibility(
    db: Session,
    doc_id: str,
    user_id: str,
):
    """切换公开状态（Issue #47）：仅所有者、未删除文档可操作。"""
    doc = (
        db.query(Document)
        .filter(
            Document.id == doc_id,
            Document.owner_id == user_id,
            Document.is_deleted == False,
        )
        .first()
    )

    if doc:
        doc.is_public = not doc.is_public
        db.commit()
        db.refresh(doc)

        return {
            "status": "success",
            "is_public": doc.is_public,
        }

    return {"error": "not found"}


def toggle_folder_public(
    db: Session,
    folder_id: str,
    user_id: str,
):
    folder = (
        db.query(Folder)
        .filter(
            Folder.id == folder_id,
            Folder.owner_id == user_id,
        )
        .first()
    )

    if not folder:
        return {"error": "文件夹不存在或无权限"}

    # Issue #48：文件夹公开状态与文档自身 is_public 是两个独立概念。
    # 开启/取消文件夹公开都只翻转文件夹状态，绝不批量修改文档公开设置。
    folder.is_public = not folder.is_public
    db.commit()

    return {
        "status": "success",
        "is_public": folder.is_public,
    }


def get_public_folders(db: Session, user_id: str = ""):
    folders = (
        db.query(Folder)
        .filter(Folder.is_public == True)
        .all()
    )

    fav_folder_ids = (
        [
            f.folder_id
            for f in db.query(FavoriteFolder)
            .filter(FavoriteFolder.user_id == user_id)
            .all()
        ]
        if user_id
        else []
    )

    return [
        {
            "id": f.id,
            "name": f.name,
            "owner_name": f.owner.nickname if f.owner else "未知",
            "is_favorited": f.id in fav_folder_ids,
        }
        for f in folders
    ]


def get_public_docs_in_folder(db: Session, folder_id: str):
    """
    公开文件夹详情（Issue #48）：文件夹须存在且公开，否则返回空列表（不泄露内容）；
    文档仍须未软删除且自身公开，与公开入口可见性过滤保持一致。
    """
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.is_public == True,
    ).first()
    if not folder:
        return []

    docs = (
        db.query(Document)
        .join(
            DocumentFolder,
            Document.id == DocumentFolder.document_id,
        )
        .filter(
            DocumentFolder.folder_id == folder_id,
            Document.is_public == True,
            Document.is_deleted == False,
        )
        .all()
    )

    return [
        {
            "id": d.id,
            "title": d.title,
            "source_type": d.source_type,
            "source_url": d.source_url,
        }
        for d in docs
    ]


def toggle_favorite_doc(
    db: Session,
    user_id: str,
    doc_id: str,
):
    """
    切换文档收藏（Issue #49）：收藏是用户私有关系，不复制、不改所有权。

    - 取消收藏（关系已存在）：只删关系，即使资源已软删除/不可见也允许清理，
      以便用户主动清理无效关系；不触碰原文档。
    - 新增收藏：必须先校验资源存在、未软删除且当前用户有权浏览
      （自有文档或公开文档），不得仅凭 doc_id 建立关系。
    """
    fav = db.query(FavoriteDocument).filter_by(
        user_id=user_id,
        document_id=doc_id,
    ).first()

    if fav:
        db.delete(fav)
        db.commit()
        return {"status": "removed"}

    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc or doc.is_deleted == True:
        return {"error": "文档不存在"}

    # Issue #54：与正文读取（#50）共用统一可见性口径（未删除 且 [所有者或公开]）。
    if not is_document_visible_to_user(doc, user_id):
        return {"error": "文档不存在或无权收藏"}

    db.add(
        FavoriteDocument(
            user_id=user_id,
            document_id=doc_id,
        )
    )
    db.commit()

    return {"status": "added"}


def toggle_favorite_folder(
    db: Session,
    user_id: str,
    folder_id: str,
):
    """
    切换文件夹收藏（Issue #49）：只允许收藏当前用户可浏览的文件夹。

    - 取消收藏：只删关系，始终允许，便于清理无效关系；不触碰原文件夹。
    - 新增收藏：校验文件夹存在且为自有或公开；收藏关系不改变所有者/公开状态。
    """
    fav = db.query(FavoriteFolder).filter_by(
        user_id=user_id,
        folder_id=folder_id,
    ).first()

    if fav:
        db.delete(fav)
        db.commit()
        return {"status": "removed"}

    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        return {"error": "文件夹不存在"}

    if folder.owner_id != user_id and not folder.is_public:
        return {"error": "文件夹不存在或无权收藏"}

    db.add(
        FavoriteFolder(
            user_id=user_id,
            folder_id=folder_id,
        )
    )
    db.commit()

    return {"status": "added"}


def get_my_favorites(db: Session, user_id: str):
    """
    当前用户的收藏列表（Issue #49）：只查询自己的收藏关系，且只返回仍可访问的资源。

    可见性按「隐藏」策略在查询层统一过滤（不主动删除关系，以便资源恢复公开/未删除后
    重新可见）：文档须未软删除且为自有或公开；文件夹须为自有或公开。
    """
    fav_docs = (
        db.query(Document)
        .join(
            FavoriteDocument,
            Document.id == FavoriteDocument.document_id,
        )
        .filter(
            FavoriteDocument.user_id == user_id,
            visible_document_condition(user_id),
        )
        .all()
    )

    fav_folders = (
        db.query(Folder)
        .join(
            FavoriteFolder,
            Folder.id == FavoriteFolder.folder_id,
        )
        .filter(
            FavoriteFolder.user_id == user_id,
            (Folder.owner_id == user_id) | (Folder.is_public == True),
        )
        .all()
    )

    return {
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "source_type": d.source_type,
                "source_url": d.source_url,
                "owner_name": d.owner.nickname if d.owner else "未知",
            }
            for d in fav_docs
        ],
        "folders": [
            {
                "id": f.id,
                "name": f.name,
                "owner_name": f.owner.nickname if f.owner else "未知",
            }
            for f in fav_folders
        ],
    }


def rename_folder(
    db: Session,
    folder_id: str,
    new_name: str,
    user_id: str,
):
    folder = (
        db.query(Folder)
        .filter(
            Folder.id == folder_id,
            Folder.owner_id == user_id,
        )
        .first()
    )

    if not folder:
        return {"error": "文件夹不存在或无权限"}

    if not new_name.strip():
        return {"error": "文件夹名不能为空"}

    folder.name = new_name
    db.commit()

    return {
        "status": "success",
        "name": folder.name,
    }


def delete_folder(
    db: Session,
    folder_id: str,
    user_id: str,
):
    folder = (
        db.query(Folder)
        .filter(
            Folder.id == folder_id,
            Folder.owner_id == user_id,
        )
        .first()
    )

    if not folder:
        return {"error": "文件夹不存在或无权限"}

    db.query(DocumentFolder).filter(
        DocumentFolder.folder_id == folder_id
    ).delete()

    db.query(FavoriteFolder).filter(
        FavoriteFolder.folder_id == folder_id
    ).delete()

    db.delete(folder)
    db.commit()

    return {"status": "success"}
