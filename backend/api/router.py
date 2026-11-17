"""统一 API 路由汇总（Issue #54 拆分）。

本文件仅负责注册各业务域的 APIRouter，不再承载任何业务实现：
- ingest：文件/URL 收录
- retrieve：知识检索
- agent：智能问答
- manage：标签、文档、文件夹、广场公开资料与收藏
- mistake：错题、复习与分析（独立 controller，Issue #53）

保持与拆分前一致的注册顺序；所有路径、HTTP 方法与请求/响应契约不变。
"""

from fastapi import APIRouter

from modules.ingest.controller.router import router as ingest_router
from modules.retrieve.controller.router import router as retrieve_router
from modules.agent.controller.router import router as agent_router
from modules.manage.controller.router import router as manage_router
from modules.mistake.controller.router import router as mistake_router


api_router = APIRouter()

api_router.include_router(mistake_router)
api_router.include_router(ingest_router)
api_router.include_router(retrieve_router)
api_router.include_router(agent_router)
api_router.include_router(manage_router)
