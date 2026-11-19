"""检索域 HTTP 路由（Issue #54 拆分，Issue #46 接入访问范围）。

仅做参数与用户上下文适配；检索由 modules.retrieve.service.search 承载。
Issue #46：把当前用户上下文传入检索服务，统一限定可见文档范围
（本人含私有 + 他人公开；排除他人私有与软删除）。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.user_context import get_current_user
from modules.ingest.domain.models import User
from modules.retrieve.service.search import search


router = APIRouter(tags=["retrieve"])


@router.get("/search")
async def search_docs(
    q: str = Query(...),
    top_k: int = 5,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Issue #46：当前用户上下文真正参与检索范围隔离。
    return await search(db, q, user_id=current_user.id, top_k=top_k)
