"""Agent 域 HTTP 路由（Issue #54 拆分）。

检索适配器在此注入（API 层提供 Adapter，Agent 服务不直接接触数据库）。
这是 Issue 要求的清晰边界表达，HTTP 契约与拆分前完全一致。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.user_context import get_current_user
from modules.ingest.domain.models import User
from modules.retrieve.service.search import search
from modules.agent.service.agent_service import agent_chat as run_agent


router = APIRouter(tags=["agent"])


class AskRequest(BaseModel):
    question: str
    top_k: int = 3


@router.post("/agent/ask")
async def agent_chat_endpoint(
    req: AskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Agent 智能问答入口。
    API 层负责提供检索接口，Agent 不直接接触数据库。
    """

    async def retrieve_adapter(
        query: str,
        requested_top_k: int
    ) -> dict:
        return await search(
            db,
            query,
            top_k=requested_top_k
        )

    return await run_agent(
        req.question,
        req.top_k,
        retrieve_adapter
    )
