"""跨模块共享的文档可见性规则（Issue #46）。

规则（用户确认的统一口径）：
- 当前用户可访问自己的文档（含私有）；
- 当前用户可访问其他用户的公开文档；
- 当前用户不可访问其他用户的私有文档；
- 已软删除文档一律不可访问。

此规则由检索（retrieve）、文档筛选（manage）、正文读取（manage）等入口共同使用，
放在 shared 层以避免 retrieve 反向依赖 manage 业务服务。

#54 起该规则定义在 manage.service.document_service，#46 上移到 shared：
- document_service 以 re-export 形式保留同名符号，folder_service / manage router
  以及既有单一定义断言（test_issue54_structure）持有的仍是同一函数对象；
- retrieve 直接依赖本模块，职责边界更清晰。
"""

import re

from sqlalchemy import and_, or_

from modules.ingest.domain.models import Document

# 与 shared.user_context 保持一致的用户 ID 形态约束，供服务层 fail-closed 校验复用。
_USER_ID_PATTERN = re.compile(r"^u_[A-Za-z0-9_]{1,64}$")


class UserScopeRequiredError(ValueError):
    """缺少有效用户上下文时抛出：拒绝执行任何用户数据范围查询（fail-closed）。"""


def require_user_id(user_id: str | None) -> str:
    """
    Issue #46 fail-closed 守卫：涉及用户数据范围的查询必须先取得有效用户 ID。

    - None / 非字符串 / 空串 / 纯空白：拒绝（不得以 user_id=None 退化为全局查询）；
    - 形态不符合 ``u_`` 前缀约定：拒绝，与 HTTP 层 get_current_user 的 400 口径一致。

    存在性校验由 HTTP 层 get_current_user（404）负责；此守卫是服务层防御纵深，
    防止任何绕过 HTTP 层的内部调用退化成无范围查询。
    """
    if not isinstance(user_id, str) or not user_id.strip():
        raise UserScopeRequiredError(
            "缺少有效的当前用户上下文，拒绝执行用户数据范围查询"
        )
    if not _USER_ID_PATTERN.match(user_id):
        raise UserScopeRequiredError(
            "用户 ID 格式无效，拒绝执行用户数据范围查询"
        )
    return user_id


def is_document_visible_to_user(doc: Document | None, user_id: str) -> bool:
    """
    对象级可见性判定：文档未软删除，且满足以下之一：
    - 当前用户是文档所有者；
    - 文档已公开。

    doc 为 None（如按 id 查不到）时一律不可见，避免泄露存在性。
    仅判定规则，不改变调用方的错误响应契约。
    """
    if doc is None:
        return False
    return (
        doc.is_deleted == False
        and (doc.owner_id == user_id or doc.is_public == True)
    )


def visible_document_condition(user_id: str | None):
    """
    与上规则等价的 SQLAlchemy 查询条件，供列表类与检索类查询在数据库层复用。

    fail-closed：user_id 缺失或无效时直接抛 UserScopeRequiredError，
    绝不生成无范围条件（旧版 user_id=None 会退化为仅排除软删的全局查询）。
    """
    user_id = require_user_id(user_id)
    return and_(
        Document.is_deleted == False,
        or_(Document.owner_id == user_id, Document.is_public == True),
    )
