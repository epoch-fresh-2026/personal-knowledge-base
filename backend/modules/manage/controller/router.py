"""资料管理域 HTTP 路由（Issue #54 拆分）。

涵盖标签、文档、文件夹、广场公开资料与收藏；仅做请求适配、错误映射与
当前用户注入，业务规则由 modules.manage.service 下各服务承载。
文档删除生命周期由 document_service 提供（Issue #54 迁入）。
路径、方法与响应契约与拆分前 api/router.py 完全一致。
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.user_context import get_current_user
from modules.ingest.domain.models import User, Document

from modules.manage.service.document_service import (
    list_documents,
    update_document_meta,
    delete_document,
    restore_document,
    permanent_delete_document,
    is_document_visible_to_user,
)
from modules.manage.service.tag_service import (
    create_tag,
    get_all_tags,
    delete_tag,
    pin_tag,
    add_tag_to_doc,
    remove_tag_from_doc,
    list_documents_by_tag,
)
from modules.manage.service.folder_service import (
    get_all_folders, create_folder, add_doc_to_folder, get_documents_in_folder,
    get_all_documents, get_uncategorized_documents, get_public_documents,
    get_user_public_docs, toggle_doc_visibility,
    get_public_folders, toggle_favorite_doc, toggle_favorite_folder, get_my_favorites,
    remove_doc_from_folder, toggle_folder_public, get_public_docs_in_folder,
    delete_folder, rename_folder,
)


router = APIRouter(tags=["manage"])


# ==================== 标签管理 ====================

class TagCreate(BaseModel):
    name: str


class DocumentUpdate(BaseModel):
    title: str | None = None
    is_public: bool | None = None
    content: str | None = None


@router.get("/tags")
async def list_tags(db: Session = Depends(get_db)):
    return get_all_tags(db)


@router.post("/tags")
async def add_tag(
    req: TagCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return create_tag(db, req.name, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/tags/{tag_id}")
async def remove_tag(
    tag_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return delete_tag(db, tag_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/tags/{tag_id}/pin")
async def toggle_tag_pin(
    tag_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 置顶是全局共享状态，所有用户看到一致结果，无需按用户过滤
    try:
        return pin_tag(db, tag_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/documents/{doc_id}/tags/{tag_id}")
async def add_document_tag(
    doc_id: str,
    tag_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return add_tag_to_doc(db, doc_id, tag_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/documents/{doc_id}/tags/{tag_id}")
async def remove_document_tag(
    doc_id: str,
    tag_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return remove_tag_from_doc(db, doc_id, tag_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/tags/{tag_name}/documents")
async def get_tag_documents(
    tag_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return list_documents_by_tag(db, tag_name, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== 文档管理 ====================

@router.get("/documents/filter")
async def filter_documents(
    owner_id: str | None = Query(None),
    keyword: str | None = Query(None),
    source_type: str | None = Query(None),
    is_public: bool | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    filters = {
        "owner_id": owner_id,
        "keyword": keyword,
        "source_type": source_type,
        "is_public": is_public
    }

    return list_documents(db, filters)


@router.put("/documents/{doc_id}/meta")
async def update_doc_meta(
    doc_id: str,
    req: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return await update_document_meta(
            db,
            doc_id,
            current_user.id,
            **req.dict(exclude_unset=True)
        )
    except ValueError as e:
        # 归属/不存在 -> 404；字段/内容不合法 -> 400（Issue #47 规则 A）
        status_code = 404 if "无权" in str(e) or "不存在" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))


# ==================== 文件夹管理 ====================

class FolderCreate(BaseModel):
    name: str


class FolderRename(BaseModel):
    new_name: str


@router.get("/folders")
async def list_folders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_all_folders(db, current_user.id)


@router.post("/folders")
async def add_folder(
    req: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return create_folder(db, req.name, current_user.id)


@router.put("/folders/{folder_id}/name")
async def rename_existing_folder(
    folder_id: str,
    req: FolderRename,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return rename_folder(db, folder_id, req.new_name, current_user.id)


@router.delete("/folders/{folder_id}")
async def delete_existing_folder(
    folder_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return delete_folder(db, folder_id, current_user.id)


@router.get("/folders/{folder_id}/documents")
async def list_folder_docs(
    folder_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_documents_in_folder(db, folder_id, current_user.id)


@router.post("/folders/{folder_id}/documents/{doc_id}")
async def move_doc(
    folder_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return add_doc_to_folder(db, doc_id, folder_id, current_user.id)


@router.delete("/folders/{folder_id}/documents/{doc_id}")
async def remove_from_folder(
    folder_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return remove_doc_from_folder(db, doc_id, folder_id, current_user.id)


@router.post("/folders/{folder_id}/toggle-public")
async def toggle_folder_visibility(
    folder_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return toggle_folder_public(db, folder_id, current_user.id)


@router.get("/documents/all")
async def list_all_docs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_all_documents(db, current_user.id)


@router.get("/documents/uncategorized")
async def list_uncategorized(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_uncategorized_documents(db, current_user.id)


@router.get("/documents/{doc_id}/content")
async def get_document_content(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 已删除文档不提供正文（Issue #47 规则 C）。
    doc = db.query(Document).filter(Document.id == doc_id).first()

    # Issue #50：正文详情与公开列表/收藏使用统一的可见性口径（Issue #54 收敛为
    # is_document_visible_to_user：未删除 且 [所有者本人 或 已公开]）。
    # 他人私有文档一律 404（不泄露存在性），防止更换 doc_id 读取私有正文。
    if not is_document_visible_to_user(doc, current_user.id):
        raise HTTPException(status_code=404, detail="文件不存在")

    full_content = "\n\n".join([c.content for c in doc.chunks])
    return {"title": doc.title, "content": full_content}


@router.post("/documents/{doc_id}/toggle-visibility")
async def toggle_visibility(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return toggle_doc_visibility(db, doc_id, current_user.id)


@router.delete("/documents/{doc_id}")
async def delete_doc(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 软删除（Issue #47 规则 C）：仅所有者可删除自己的文档
    return delete_document(db, doc_id, current_user.id)


@router.post("/documents/{doc_id}/restore")
async def restore_doc(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 恢复软删除文档（Issue #47 规则 C）：仅所有者可恢复
    return restore_document(db, doc_id, current_user.id)


@router.delete("/documents/{doc_id}/permanent")
async def permanent_delete_doc(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 彻底删除（Issue #47 规则 C）：仅所有者可操作，含关联数据与文件清理
    return permanent_delete_document(db, doc_id, current_user.id)


# ==================== 广场与公开资料 ====================

@router.get("/square")
async def get_square(
    keyword: str = Query(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_public_documents(db, keyword, current_user.id)


@router.get("/square/folders")
async def square_folders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_public_folders(db, current_user.id)


@router.get("/square/folders/{folder_id}/docs")
async def get_square_folder_docs(
    folder_id: str,
    db: Session = Depends(get_db)
):
    return get_public_docs_in_folder(db, folder_id)


@router.get("/users/{author_id}/docs")
async def user_profile(author_id: str, db: Session = Depends(get_db)):
    """
    作者主页：路径参数是"目标作者"，不是当前操作者（Issue #45）。

    这里只按目标作者返回其公开文档，不读取或覆盖当前操作者身份。
    公开范围规则由 #50 细化。
    """
    return get_user_public_docs(db, author_id)


# ==================== 收藏 ====================

@router.post("/favorites/doc/{doc_id}")
async def fav_doc(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return toggle_favorite_doc(db, current_user.id, doc_id)


@router.post("/favorites/folder/{folder_id}")
async def fav_folder(
    folder_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return toggle_favorite_folder(db, current_user.id, folder_id)


@router.get("/favorites")
async def my_favorites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_my_favorites(db, current_user.id)
