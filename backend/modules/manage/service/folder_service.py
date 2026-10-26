from sqlalchemy.orm import Session
from modules.manage.domain.models import Folder, DocumentFolder, FavoriteFolder
from modules.ingest.domain.models import Document, User, FavoriteDocument
from uuid import uuid4
from sqlalchemy import select # 👈 确保顶部导入了 select
import os

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

def remove_doc_from_folder(db: Session, doc_id: str, folder_id: str):
    df = db.query(DocumentFolder).filter_by(document_id=doc_id, folder_id=folder_id).first()
    if df:
        db.delete(df)
        db.commit()
    return {"status": "success"}

def delete_document(db: Session, doc_id: str):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return {"error": "文档不存在"}

    if doc.source_url and doc.source_url.startswith("/uploads/"):
        file_path = doc.source_url.replace("/uploads/", "uploads/", 1)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"物理文件删除失败: {e}")

    db.query(DocumentFolder).filter(DocumentFolder.document_id == doc_id).delete()
    db.query(FavoriteDocument).filter(FavoriteDocument.document_id == doc_id).delete()
    db.delete(doc)
    db.commit()
    return {"status": "success"}

def get_documents_in_folder(db: Session, folder_id: str):
    docs = db.query(Document).join(DocumentFolder, Document.id == DocumentFolder.document_id).filter(DocumentFolder.folder_id == folder_id).all()
    return [{
        "id": d.id, "title": d.title, "source_type": d.source_type, 
        "source_url": d.source_url, "is_public": d.is_public, "owner_id": d.owner_id
    } for d in docs]

# 👇 修复漏洞 1：按 user_id 过滤
def get_all_documents(db: Session, user_id: str):
    docs = db.query(Document).filter(Document.owner_id == user_id).order_by(Document.created_at.desc()).all()
    return [{
        "id": d.id, "title": d.title, "source_type": d.source_type, 
        "source_url": d.source_url, "is_public": d.is_public, "owner_id": d.owner_id
    } for d in docs]

# 👇 修复漏洞 2：按 user_id 过滤
def get_uncategorized_documents(db: Session, user_id: str):
    subquery = db.query(DocumentFolder.document_id)
    docs = db.query(Document).filter(
        ~Document.id.in_(subquery),
        Document.owner_id == user_id # 👈 增加这个过滤条件
    ).order_by(Document.created_at.desc()).all()
    return [{
        "id": d.id, "title": d.title, "source_type": d.source_type, 
        "source_url": d.source_url, "is_public": d.is_public, "owner_id": d.owner_id
    } for d in docs]

def get_public_documents(db: Session, keyword: str = "", user_id: str = ""):
    # 1. 找出所有公开文件夹的 ID
    public_folder_ids = db.query(Folder.id).filter(Folder.is_public == True).subquery()
    # 2. 找出在公开文件夹里的文档 ID
    doc_ids_in_public_folders = db.query(DocumentFolder.document_id).filter(DocumentFolder.folder_id.in_(select(public_folder_ids))).subquery()
    
    # 3. 查询文档：必须是公开的，且【不在】任何公开文件夹内
    query = db.query(Document).filter(
        Document.is_public == True,
        ~Document.id.in_(doc_ids_in_public_folders) # 👈 核心：排除已在公开文件夹内的
    )
    
    if keyword:
        query = query.join(User, Document.owner_id == User.id, isouter=True).filter(
            (Document.title.like(f"%{keyword}%")) | (User.nickname.like(f"%{keyword}%"))
        )
    docs = query.all()
    fav_doc_ids = [f.document_id for f in db.query(FavoriteDocument).filter(FavoriteDocument.user_id == user_id).all()] if user_id else []
    
    return [{
        "id": d.id, "title": d.title, "source_type": d.source_type, "source_url": d.source_url,
        "author_name": d.owner.nickname if d.owner else "未知", 
        "author_avatar": d.owner.avatar if d.owner else "👤", 
        "author_id": d.owner_id if d.owner_id else "unknown",
        "is_favorited": d.id in fav_doc_ids
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

def toggle_folder_public(db: Session, folder_id: str, user_id: str):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == user_id).first()
    if not folder:
        return {"error": "文件夹不存在或无权限"}
    
    folder.is_public = not folder.is_public
    if folder.is_public:
        docs = db.query(Document).join(DocumentFolder, Document.id == DocumentFolder.document_id).filter(DocumentFolder.folder_id == folder_id).all()
        for doc in docs:
            doc.is_public = True
    db.commit()
    return {"status": "success", "is_public": folder.is_public}

def get_public_folders(db: Session, user_id: str = ""):
    folders = db.query(Folder).filter(Folder.is_public == True).all()
    fav_folder_ids = [f.folder_id for f in db.query(FavoriteFolder).filter(FavoriteFolder.user_id == user_id).all()] if user_id else []
    return [{
        "id": f.id, "name": f.name, 
        "owner_name": f.owner.nickname if f.owner else "未知",
        "is_favorited": f.id in fav_folder_ids
    } for f in folders]

def get_public_docs_in_folder(db: Session, folder_id: str):
    docs = db.query(Document).join(DocumentFolder, Document.id == DocumentFolder.document_id).filter(
        DocumentFolder.folder_id == folder_id,
        Document.is_public == True
    ).all()
    return [{"id": d.id, "title": d.title, "source_type": d.source_type, "source_url": d.source_url} for d in docs]

def toggle_favorite_doc(db: Session, user_id: str, doc_id: str):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return {"error": "文档不存在"}
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
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        return {"error": "文件夹不存在"}
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
            "id": d.id, "title": d.title, "source_type": d.source_type, "source_url": d.source_url,
            "owner_name": d.owner.nickname if d.owner else "未知"
        } for d in fav_docs],
        "folders": [{"id": f.id, "name": f.name, "owner_name": f.owner.nickname if f.owner else "未知"} for f in fav_folders]
    }

def rename_folder(db: Session, folder_id: str, new_name: str, user_id: str):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == user_id).first()
    if not folder:
        return {"error": "文件夹不存在或无权限"}
    if not new_name.strip():
        return {"error": "文件夹名不能为空"}
    folder.name = new_name
    db.commit()
    return {"status": "success", "name": folder.name}

def delete_folder(db: Session, folder_id: str, user_id: str):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == user_id).first()
    if not folder:
        return {"error": "文件夹不存在或无权限"}
    db.query(DocumentFolder).filter(DocumentFolder.folder_id == folder_id).delete()
    db.query(FavoriteFolder).filter(FavoriteFolder.folder_id == folder_id).delete()
    db.delete(folder)
    db.commit()
    return {"status": "success"}