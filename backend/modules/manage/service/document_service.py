"""文档领域服务（Issue #54 工程整理）。

统一承载文档元信息、列表查询，以及文档的完整删除生命周期
（软删除 / 恢复 / 永久删除及其孤立文件补偿，原位于 folder_service，Issue #47）。

删除生命周期的函数体自 Issue #47 起逐字搬迁，业务语义与失败补偿规则不变；
本次仅做「位置迁移」，以便文档相关规则集中在文档服务内。
"""

import json
import os
from datetime import datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from modules.ingest.domain.models import Document, FavoriteDocument, Chunk
from modules.manage.domain.models import DocumentFolder, DocumentTag


# ==================== 文档归属与元信息 ====================

# 允许通过元信息接口修改的字段（Issue #47 规则 A）：
# 仅标题、公开状态等元信息；原始内容 content 不允许在此修改（需重新收录）。
ALLOWED_META_FIELDS = {"title", "is_public"}


def _get_document_for_owner(
    db: Session,
    doc_id: str,
    user_id: str,
    *,
    is_deleted: bool,
) -> Document | None:
    """
    统一的文档归属查询（Issue #47 规则 C / Issue #54 整理）：
    文档 ID + 所有者必须为当前用户 + 指定删除状态。

    软删除（is_deleted=False）与恢复/永久删除（is_deleted=True）共用此口径，
    仅删除状态参数不同，确保「谁能操作谁的文档」只有一处定义。
    """
    return (
        db.query(Document)
        .filter(
            Document.id == doc_id,
            Document.owner_id == user_id,
            Document.is_deleted == is_deleted,
        )
        .first()
    )


def _get_owned_document(db: Session, doc_id: str, user_id: str) -> Document | None:
    """查询当前用户拥有的、未删除的文档（统一归属判断，Issue #47）。"""
    return _get_document_for_owner(db, doc_id, user_id, is_deleted=False)


async def update_document_meta(db: Session, doc_id: str, user_id: str, **kwargs):
    """
    更新文档元信息（Issue #47 规则 A）。

    - 仅当前用户拥有的、未删除的文档可修改；
    - 只允许 title / is_public 等元信息字段；
    - 不修改原始内容、不重建 chunks、不重新生成 Embedding。
    """
    doc = _get_owned_document(db, doc_id, user_id)

    if not doc:
        raise ValueError("文档不存在或无权操作")

    unknown_fields = set(kwargs.keys()) - ALLOWED_META_FIELDS
    if unknown_fields:
        raise ValueError(f"不支持修改的字段：{unknown_fields}")

    try:
        if "title" in kwargs:
            title = kwargs["title"]
            if not title or not title.strip():
                raise ValueError("文档标题不能为空")
            doc.title = title.strip()

        if "is_public" in kwargs:
            doc.is_public = kwargs["is_public"]

        db.commit()
        db.refresh(doc)
        return doc

    except Exception:
        db.rollback()
        raise


def is_document_visible_to_user(doc: Document | None, user_id: str) -> bool:
    """
    统一的「文档可见性」判定（Issue #49 / #50 共用口径，Issue #54 整理）：

    文档未软删除，且满足以下之一：
    - 当前用户是文档所有者；
    - 文档已公开。

    将该复合规则收敛到单一函数，避免正文读取（#50）与收藏新增（#49）
    各自实现出不同版本。此函数只判定规则，不改变调用方的错误响应契约。
    """
    if doc is None:
        return False
    return (
        doc.is_deleted == False
        and (doc.owner_id == user_id or doc.is_public == True)
    )


def visible_document_condition(user_id: str):
    """
    与上规则等价的 SQLAlchemy 查询条件（Issue #54 整理）：
    供列表类查询（如收藏列表）在数据库层复用同一可见性口径，
    避免各入口各写一份 is_deleted / owner / is_public 组合。
    """
    return and_(
        Document.is_deleted == False,
        or_(Document.owner_id == user_id, Document.is_public == True),
    )


def list_documents(db: Session, filters: dict | None = None):
    """根据筛选条件获取文档列表（排除已删除文档，Issue #47）。"""
    filters = filters or {}
    query = db.query(Document).filter(Document.is_deleted == False)

    owner_id = filters.get("owner_id")
    if owner_id:
        query = query.filter(Document.owner_id == owner_id)

    keyword = filters.get("keyword")
    if keyword and keyword.strip():
        query = query.filter(
            Document.title.like(f"%{keyword.strip()}%")
        )

    source_type = filters.get("source_type")
    if source_type:
        query = query.filter(Document.source_type == source_type)

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


# ==================== 文档删除生命周期（Issue #47，Issue #54 迁入） ====================

# 彻底删除时待清理文件的持久化清单（Issue #47 最后补充核查）。
# 位置：uploads 目录下，仅记录 /uploads/ 相对路径，不落绝对磁盘路径。
# 采用「预登记（write-ahead intent）」：在数据库删除之前先原子写入清单，
# 从而消除「DB 已删、清单未登记」的崩溃窗口，并让清单写入失败可安全中止删除。
ORPHAN_CLEANUP_FILE = os.path.join("uploads", ".orphan_cleanup.json")

# 清单条目阶段：
# - pending：预登记完成，但数据库删除尚未确认提交；
# - confirmed：数据库已删除，物理文件待清理（历史无 phase 条目按此兼容）。
_PHASE_PENDING = "pending"
_PHASE_CONFIRMED = "confirmed"


def _is_safe_relative_filename(rel: str | None) -> bool:
    """校验清单中存储的相对文件名是否安全：必须是单一文件名、无路径穿越。"""
    if not rel or rel != os.path.basename(rel) or ".." in rel:
        return False
    if "/" in rel or "\\" in rel:
        return False
    return True


def _safe_upload_rel_path(source_url: str | None) -> str | None:
    """
    把 /uploads/xxx 形式的安全 source_url 转成 uploads 下的相对文件名。
    仅接受以 /uploads/ 开头、且不含路径穿越片段（/、\\、..）的单一文件名，
    防止误删其他文档文件或目录穿越。返回 None 表示无需/不应清理文件。
    """
    if not source_url or not source_url.startswith("/uploads/"):
        return None
    rel = source_url[len("/uploads/"):]
    return rel if _is_safe_relative_filename(rel) else None


def _load_orphan_cleanup() -> list[dict]:
    """读取待清理清单；不存在或损坏时返回空列表。历史条目补齐 phase 以兼容。"""
    if not os.path.exists(ORPHAN_CLEANUP_FILE):
        return []
    try:
        with open(ORPHAN_CLEANUP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    entries = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        normalized.setdefault("phase", _PHASE_CONFIRMED)
        entries.append(normalized)
    return entries


def _save_orphan_cleanup(entries: list[dict]) -> None:
    """原子写入待清理清单：临时文件 + os.replace，避免中断造成 JSON 损坏。"""
    directory = os.path.dirname(ORPHAN_CLEANUP_FILE) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = ORPHAN_CLEANUP_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ORPHAN_CLEANUP_FILE)
    finally:
        # 任何失败路径都清理临时文件，避免残留 .tmp 干扰后续读取/审计。
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def record_orphan_file(doc_id: str, source_url: str) -> None:
    """历史兼容入口：直接登记一条「已确认」的孤立文件记录（同一路径幂等）。"""
    rel = _safe_upload_rel_path(source_url)
    if rel is None:
        return
    entries = _load_orphan_cleanup()
    if any(e.get("path") == rel for e in entries):
        return
    entries.append({"doc_id": doc_id, "path": rel, "phase": _PHASE_CONFIRMED})
    _save_orphan_cleanup(entries)


def register_cleanup_intent(doc_id: str, source_url: str) -> str | None:
    """
    Write-ahead 预登记：在数据库删除之前原子写入待清理意图。

    返回安全相对文件名；source_url 无需清理时返回 None。
    写入失败直接抛出 OSError，由调用方决定中止删除，避免产生不可追踪的孤立文件。
    """
    rel = _safe_upload_rel_path(source_url)
    if rel is None:
        return None
    entries = _load_orphan_cleanup()
    if not any(e.get("path") == rel for e in entries):
        entries.append({"doc_id": doc_id, "path": rel, "phase": _PHASE_PENDING})
    _save_orphan_cleanup(entries)
    return rel


def confirm_cleanup_intent(doc_id: str, rel: str) -> None:
    """数据库删除提交成功后，把预登记条目标记为 confirmed（可安全清理）。"""
    entries = _load_orphan_cleanup()
    changed = False
    for entry in entries:
        if entry.get("path") == rel and entry.get("phase") == _PHASE_PENDING:
            entry["phase"] = _PHASE_CONFIRMED
            entry["doc_id"] = doc_id
            changed = True
    if changed:
        _save_orphan_cleanup(entries)


def clear_cleanup_intent(doc_id: str, rel: str) -> None:
    """文件已清理或数据库删除失败时，撤销对应清单条目（幂等）。"""
    entries = _load_orphan_cleanup()
    kept = [
        e for e in entries
        if not (e.get("path") == rel and e.get("doc_id") == doc_id)
    ]
    if len(kept) != len(entries):
        _save_orphan_cleanup(kept)


def _document_still_exists(db: Session, doc_id: str | None) -> bool:
    """判断预登记对应的文档是否仍在库中；无 id 或查询失败时保守视为仍存在。"""
    if not doc_id:
        return True
    try:
        return db.query(Document).filter(Document.id == doc_id).first() is not None
    except Exception:
        return True


def retry_orphan_file_cleanup(db: Session | None = None) -> dict:
    """
    幂等重试孤立文件清理：扫描清单，逐个安全删除；文件不存在视为成功。
    返回 {'attempted': n, 'cleaned': n, 'remaining': n}。

    崩溃恢复语义（Issue #47 最后补充核查）：
    - confirmed 条目：数据库删除已确认，可直接清理文件；
    - pending 条目：进程可能在「预登记后、DB 删除前」崩溃，此时文档仍在库中，
      文件不能删。若传入 db，则据此判断：文档仍在→撤销未完成意图；
      文档已不在→说明 DB 删除已完成，确认意图并清理文件。
      未传 db 时保守保留 pending 条目，绝不盲目删除可能仍被文档引用的文件。
    """
    entries = _load_orphan_cleanup()
    remaining: list[dict] = []
    cleaned = 0
    attempted = 0
    changed = False

    for entry in entries:
        rel = entry.get("path", "")
        if not _is_safe_relative_filename(rel):
            # 非法路径直接丢弃，不尝试删除（防误删）
            changed = True
            continue

        if entry.get("phase", _PHASE_CONFIRMED) == _PHASE_PENDING:
            if db is None:
                remaining.append(entry)
                continue
            if _document_still_exists(db, entry.get("doc_id")):
                # DB 删除未完成：撤销未确认的意图，避免误删仍属于该文档的文件
                changed = True
                continue
            # DB 删除已完成（曾崩溃于此窗口）：确认意图后继续清理
            entry["phase"] = _PHASE_CONFIRMED
            changed = True

        attempted += 1
        file_path = os.path.join("uploads", rel)
        if not os.path.exists(file_path):
            cleaned += 1  # 文件已不在，视为清理成功（幂等）
            changed = True
            continue
        try:
            os.remove(file_path)
            cleaned += 1
            changed = True
        except OSError:
            remaining.append(entry)

    if changed or len(remaining) != len(entries):
        _save_orphan_cleanup(remaining)

    return {
        "attempted": attempted,
        "cleaned": cleaned,
        "remaining": len(remaining),
    }


def delete_document(db: Session, doc_id: str, user_id: str):
    """
    软删除文档（Issue #47 规则 C）。

    仅校验当前用户拥有的、未删除的文档；删除只标记 is_deleted / deleted_at，
    不删除关联数据、不删除本地文件、不执行物理删除。
    恢复与彻底删除分别由 restore_document / permanent_delete_document 处理。
    """
    doc = _get_document_for_owner(db, doc_id, user_id, is_deleted=False)

    if not doc:
        return {"error": "文档不存在或无权操作"}

    doc.is_deleted = True
    doc.deleted_at = datetime.utcnow()
    db.commit()

    return {"status": "success", "is_deleted": True}


def restore_document(db: Session, doc_id: str, user_id: str):
    """恢复软删除的文档（Issue #47 规则 C）：仅所有者可恢复。"""
    doc = _get_document_for_owner(db, doc_id, user_id, is_deleted=True)

    if not doc:
        return {"error": "文档不存在或无权操作"}

    doc.is_deleted = False
    doc.deleted_at = None
    db.commit()

    return {"status": "success", "is_deleted": False}


def permanent_delete_document(db: Session, doc_id: str, user_id: str):
    """
    彻底删除文档（Issue #47 规则 C）：仅所有者可操作。

    事务/补偿策略（Issue #47 最后补充核查后完善）：
    0. 先幂等重试历史清单（自愈，带 db 以判定未确认意图）；
    1. 数据库删除之前先原子「预登记」待清理文件（write-ahead intent）。
       若清单写入失败则中止删除，避免产生不可追踪的孤立文件；
    2. 在数据库事务内删除文档及其 chunks、文件夹/标签/收藏关联，提交；
       数据库删除失败则撤销预登记，避免后续误判；
    3. 数据库提交成功后确认意图，再用安全路径清理本地上传文件；
    4. 文件清理失败不回滚已提交的数据库（保持原有失败不回滚语义），
       预登记记录保留在清单中，可通过 retry_orphan_file_cleanup 幂等重试；
       进程在「预登记后、文件删除前」崩溃时，重启后由带 db 的 retry 依据
       数据库状态决定确认清理或撤销意图，从而恢复追踪。
    """
    doc = _get_document_for_owner(db, doc_id, user_id, is_deleted=True)

    if not doc:
        return {"error": "文档不存在或无权操作"}

    source_url = doc.source_url

    # 0. 自愈历史清单（带 db：pending 意图可据此判定，避免误删仍存在的文档文件）
    try:
        retry_orphan_file_cleanup(db)
    except OSError as cleanup_error:
        # 自愈失败不阻断本次删除，主流程继续
        print(f"孤立文件自愈重试失败（不阻断删除）: {cleanup_error}")

    # 1. Write-ahead 预登记：DB 删除前先原子写入清单，消除「DB 已删、清单未登记」窗口。
    rel = _safe_upload_rel_path(source_url)
    if rel is not None:
        try:
            register_cleanup_intent(doc_id, source_url)
        except OSError as e:
            # 无法保证可追踪性：不删 DB、不删文件，返回明确错误。
            # 这不属于「文件删除失败回滚 DB」的语义变更（尚未进入 DB 删除阶段）。
            return {
                "error": "无法登记文件清理清单，已中止删除以保证可追踪性",
                "detail": str(e),
            }

    # 2. 数据库事务：关联数据与文档一并清理
    try:
        db.query(Chunk).filter(
            Chunk.document_id == doc_id
        ).delete(synchronize_session=False)

        db.query(DocumentFolder).filter(
            DocumentFolder.document_id == doc_id
        ).delete(synchronize_session=False)

        db.query(FavoriteDocument).filter(
            FavoriteDocument.document_id == doc_id
        ).delete(synchronize_session=False)

        db.query(DocumentTag).filter(
            DocumentTag.document_id == doc_id
        ).delete(synchronize_session=False)

        db.delete(doc)
        db.commit()
    except Exception:
        db.rollback()
        # DB 删除失败：撤销预登记，避免后续 retry 误删仍属于该文档的文件
        if rel is not None:
            try:
                clear_cleanup_intent(doc_id, rel)
            except OSError:
                pass
        raise

    # 3. DB 已提交：确认意图（此后即使崩溃，retry(db) 也能凭 DB 状态完成恢复）
    if rel is not None:
        try:
            confirm_cleanup_intent(doc_id, rel)
        except OSError:
            # 清单仍为 pending；下次 retry(db) 发现文档已不在 → 自动确认并清理
            pass

    # 4. 物理文件清理（安全路径，防误删；失败不回滚数据库）
    file_cleanup = "not_applicable"
    if rel is not None:
        file_path = os.path.join("uploads", rel)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                file_cleanup = "success"
                try:
                    clear_cleanup_intent(doc_id, rel)
                except OSError:
                    # 清单残留指向已不存在的文件，retry 视为清理成功（幂等）
                    pass
            except OSError as e:
                # 文件清理失败：预登记记录已保证可追踪，不回滚已提交的 DB。
                file_cleanup = f"failed: {e}; 已登记待清理清单（可幂等重试）"
                print(f"彻底删除：物理文件清理失败（数据库已删除）: {e}")
        else:
            # 文件已不存在，撤销意图，保持清单干净
            try:
                clear_cleanup_intent(doc_id, rel)
            except OSError:
                pass

    return {"status": "success", "file_cleanup": file_cleanup}
