"""检索域 HTTP 路由（Issue #54 拆分）。

仅做参数与用户上下文适配；检索由 modules.retrieve.service.search 承载。
检索范围规则按既定约定留待 #46 处理，本 Issue 不改变其行为（决策 3）；
软删除文档不进入检索结果的规则由 search.py 保持（Issue #47）。
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
    # 仅接入当前用户上下文；检索范围过滤规则由 #46 实现（本 Issue 不提前处理）
    return await search(db, q, top_k=top_k)
