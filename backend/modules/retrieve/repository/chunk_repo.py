from sqlalchemy.orm import Session

from modules.ingest.domain.models import Chunk
from shared.document_visibility import require_user_id, visible_document_condition


def search_by_keywords(
    db: Session,
    keywords: list[str],
    user_id: str | None = None,
    top_k: int = 5,
) -> list[Chunk]:
    """
    关键词检索：对每个关键词做 LIKE 匹配，去重后返回。
    简单版：不考虑相关度排序（用 Python 再算）。

    可见范围（Issue #46）：复用 shared 的统一可见条件——本人（含私有）+
    他人公开，排除他人私有与所有软删除文档。

    fail-closed（最终验收）：缺少有效 user_id 直接拒绝，不退化为仅排除软删的
    全局查询。所有检索 HTTP 入口均经 get_current_user 注入有效用户 ID。
    """
    # fail-closed：无效用户上下文直接拒绝，绝不返回全局数据。
    user_id = require_user_id(user_id)

    if not keywords:
        return []

    from sqlalchemy import or_
    conditions = [Chunk.content.like(f"%{kw}%") for kw in keywords]

    chunks = (
        db.query(Chunk)
        .filter(
            Chunk.document.has(visible_document_condition(user_id)),
            or_(*conditions),
        )
        .all()
    )

    # Python 里算命中数排序
    def hit_count(chunk: Chunk) -> int:
        return sum(1 for kw in keywords if kw in chunk.content)

    chunks.sort(key=hit_count, reverse=True)
    return chunks[:top_k]
