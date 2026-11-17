"""收录域 HTTP 路由（Issue #54 拆分）。

仅负责请求解析、当前用户依赖注入与错误映射；解析/切分/Embedding/持久化
业务由 modules.ingest.service.ingest_service 承载（Issue #52）。
路径、方法与响应契约与拆分前 api/router.py 完全一致。
"""

from fastapi import APIRouter, UploadFile, File, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.user_context import get_current_user
from modules.ingest.domain.models import User
from modules.ingest.service.ingest_service import (
    IngestError,
    ingest_upload_file,
    ingest_web_url,
)


router = APIRouter(tags=["ingest"])


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    is_public: bool = Query(False),
    db: Session = Depends(get_db)
):
    """文件收录：统一流程与失败补偿由 ingest_service 负责（Issue #52）。"""
    file_bytes = await file.read()
    try:
        return await ingest_upload_file(
            db,
            file_bytes,
            file.filename,
            is_public,
            current_user.id,
        )
    except IngestError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


class URLCreate(BaseModel):
    url: str
    is_public: bool = False


@router.post("/documents/url")
async def ingest_url(
    req: URLCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """URL 收录：基础校验、原始 source_url 与失败补偿由 ingest_service 负责（Issue #52）。"""
    try:
        return await ingest_web_url(
            db,
            req.url,
            req.is_public,
            current_user.id,
        )
    except IngestError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
