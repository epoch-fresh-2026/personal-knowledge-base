from sqlalchemy.orm import Session
from modules.manage.domain.models import Folder, DocumentFolder, FavoriteFolder
from modules.ingest.domain.models import Document, User, FavoriteDocument
from uuid import uuid4

def create_folder(db: Session, name: str, owner_id: str):
    folder = Folder(id=str(uuid4()), name=name, owner_id=owner_id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder

def get_all_folders(db: Session, user_id: str):
    folders = db.query(Folder).filter(Folder.owner_id == user_id).all()
    return [{"id": f.id, "name": f.name, "is_public": f.is_public} for f in folders]

def add_doc_to_folder(db: Session, doc_id: str, folder_id: str):
    exists = db.query(DocumentFolder).filter_by(document_id=doc_id, folder_id=folder_id).first()
    if not exists:
        df = DocumentFolder(document_id=doc_id, folder_id=folder_id)
        db.add(df)
        db.commit()
    return {"status": "success"}

# 👇 修改 1：加上了 source_url 和 source_type
def get_documents_in_folder(db: Session, folder_id: str):
    docs = db.query(Document).join(DocumentFolder, Document.id == DocumentFolder.document_id).filter(DocumentFolder.folder_id == folder_id).all()
    return [{
        "id": d.id, 
        "title": d.title, 
        "source_type": d.source_type, 
        "source_url": d.source_url, # 👈 新增
        "is_public": d.is_public, 
        "owner_id": d.owner_id
    } for d in docs]

# 👇 修改 2：加上了 source_url 和 source_type
def get_all_documents(db: Session):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [{
        "id": d.id, 
        "title": d.title, 
        "source_type": d.source_type, 
        "source_url": d.source_url, # 👈 新增
        "is_public": d.is_public, 
        "owner_id": d.owner_id
    } for d in docs]

# 👇 修改 3：加上了 source_url 和 source_type
def get_uncategorized_documents(db: Session):
    subquery = db.query(DocumentFolder.document_id)
    docs = db.query(Document).filter(~Document.id.in_(subquery)).order_by(Document.created_at.desc()).all()
    return [{
        "id": d.id, 
        "title": d.title, 
        "source_type": d.source_type, 
        "source_url": d.source_url, # 👈 新增
        "is_public": d.is_public, 
        "owner_id": d.owner_id
    } for d in docs]

def get_public_documents(db: Session, keyword: str = ""):
    query = db.query(Document).filter(Document.is_public == True)
    if keyword:
        query = query.join(User, Document.owner_id == User.id, isouter=True).filter(
            (Document.title.like(f"%{keyword}%")) | (User.nickname.like(f"%{keyword}%"))
        )
    docs = query.all()
    return [{
        "id": d.id, 
        "title": d.title, 
        "source_type": d.source_type, 
        "source_url": d.source_url, # 👈 这里也加上，方便广场里也能预览
        "author_name": d.owner.nickname if d.owner else "未知", 
        "author_avatar": d.owner.avatar if d.owner else "👤", 
        "author_id": d.owner_id if d.owner_id else "unknown"
    } for d in docs]

def get_user_public_docs(db: Session, user_id: str):
    docs = db.query(Document).filter(Document.is_public == True, Document.owner_id == user_id).all()
    return [{"id": d.id, "title": d.title, "source_type": d.source_type} for d in docs]

def toggle_doc_visibility(db: Session, doc_id: str, user_id: str):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc:
        doc.is_public = not doc.is_public
        db.commit()
        db.refresh(doc)
        return {"status": "success", "is_public": doc.is_public}
    return {"error": "not found"}

def get_public_folders(db: Session):
    folders = db.query(Folder).filter(Folder.is_public == True).all()
    return [{"id": f.id, "name": f.name, "owner_name": f.owner.nickname if f.owner else "未知"} for f in folders]

def toggle_favorite_doc(db: Session, user_id: str, doc_id: str):
    fav = db.query(FavoriteDocument).filter_by(user_id=user_id, document_id=doc_id).first()
    if fav:
        db.delete(fav)
        db.commit()
        return {"status": "removed"}
    else:
        db.add(FavoriteDocument(user_id=user_id, document_id=doc_id))
        db.commit()
        return {"status": "added"}

def toggle_favorite_folder(db: Session, user_id: str, folder_id: str):
    fav = db.query(FavoriteFolder).filter_by(user_id=user_id, folder_id=folder_id).first()
    if fav:
        db.delete(fav)
        db.commit()
        return {"status": "removed"}
    else:
        db.add(FavoriteFolder(user_id=user_id, folder_id=folder_id))
        db.commit()
        return {"status": "added"}

def get_my_favorites(db: Session, user_id: str):
    fav_docs = db.query(Document).join(FavoriteDocument, Document.id == FavoriteDocument.document_id).filter(FavoriteDocument.user_id == user_id).all()
    fav_folders = db.query(Folder).join(FavoriteFolder, Folder.id == FavoriteFolder.folder_id).filter(FavoriteFolder.user_id == user_id).all()
    
    return {
        "documents": [{
            "id": d.id, 
            "title": d.title, 
            "source_type": d.source_type, # 👈 加上这个
            "source_url": d.source_url,   # 👈 加上这个，方便在收藏页也能预览图片视频
            "owner_name": d.owner.nickname if d.owner else "未知"
        } for d in fav_docs],
        "folders": [{"id": f.id, "name": f.name, "owner_name": f.owner.nickname if f.owner else "未知"} for f in fav_folders]
    }

import os

def remove_doc_from_folder(db: Session, doc_id: str, folder_id: str):
    """将文档移出指定的收藏夹"""
    df = db.query(DocumentFolder).filter_by(document_id=doc_id, folder_id=folder_id).first()
    if df:
        db.delete(df)
        db.commit()
    return {"status": "success"}

def delete_document(db: Session, doc_id: str):
    """彻底删除文档（包括本地物理文件、切片、关联关系）"""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return {"error": "文档不存在"}

    # 1. 删除本地物理文件
    if doc.source_url and doc.source_url.startswith("/uploads/"):
        # 把 URL 转换成物理路径，例如把 /uploads/xxx 变成 uploads/xxx
        file_path = doc.source_url.replace("/uploads/", "uploads/", 1)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"物理文件删除失败: {e}")

    # 2. 删除数据库中的切片和关联关系
    # (因为我们设了 cascade="all, delete-orphan"，删除 doc 会自动删 chunk)
    db.query(DocumentFolder).filter(DocumentFolder.document_id == doc_id).delete()
    db.query(FavoriteDocument).filter(FavoriteDocument.document_id == doc_id).delete()
    db.delete(doc)
    db.commit()
    
    return {"status": "success"}