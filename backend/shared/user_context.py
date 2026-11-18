import re

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from shared.db import get_db
from modules.ingest.domain.models import User

# ID 形态约束：以 u_ 开头，后接字母、数字、下划线，长度受限。
# 后端只校验形态与"数据库中是否存在"；允许名单属于前端职责。
_USER_ID_PATTERN = re.compile(r"^u_[A-Za-z0-9_]{1,64}$")


def validate_user_id_format(user_id: str) -> str:
    """
    校验当前模拟用户 ID 的形态。

    - 缺失由 FastAPI 的 Query(...) 处理，返回 422。
    - 这里只处理"格式错误"，返回 400；不存在另行返回 404。
    """
    if not isinstance(user_id, str) or not _USER_ID_PATTERN.match(user_id):
        raise HTTPException(
            status_code=400,
            detail="用户 ID 格式无效",
        )
    return user_id


def get_current_user(
    user_id: str = Query(
        ...,
        description="当前模拟用户 ID（模拟用户切换，非真实身份认证）",
    ),
    db: Session = Depends(get_db),
) -> User:
    """
    获取并校验当前模拟用户（Issue #45）。

    前端必须明确传入 user_id，后端不再默认使用张三。

    错误语义：
    - 缺少 user_id：由 Query(...) 返回 422；
    - 格式错误：validate_user_id_format 返回 400；
    - 数据库中不存在：返回 404。

    注意：这是模拟用户切换，不是真实身份认证，不构成安全边界。
    """
    validate_user_id_format(user_id)

    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="用户不存在",
        )

    return user
