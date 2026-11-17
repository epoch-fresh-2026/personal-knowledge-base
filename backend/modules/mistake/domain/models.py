"""错题模块领域模型（Issue #53）。

Mistake 与 MistakeReviewRecord 的唯一正式定义位于此模块。
旧路径 modules.ingest.domain.models 仅做向后兼容重导出，
两者导入得到的是同一个 ORM 类对象，不会产生两套表映射。

外键使用字符串引用 "users.id" / "mistakes.id"，无需导入 User，
避免 mistake 与 ingest 模块之间的循环导入。
"""

from datetime import datetime

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from shared.db import Base


class Mistake(Base):
    __tablename__ = "mistakes"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    question = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=True)
    wrong_answer = Column(Text, nullable=True)
    error_reason = Column(Text, nullable=True)
    knowledge_points = Column(Text, nullable=True)

    # 复习状态：pending、reviewing、mastered
    status = Column(String, default="pending", nullable=False)

    # 累计复习次数
    review_count = Column(Integer, default=0, nullable=False)

    # 最近一次复习时间
    last_reviewed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # 一道错题可以有多条复习记录（Issue #53：ORM relationship 级联删除）
    review_records = relationship(
        "MistakeReviewRecord",
        back_populates="mistake",
        cascade="all, delete-orphan",
    )


class MistakeReviewRecord(Base):
    """
    错题复习历史记录。
    每完成一次复习，就保存一条独立记录。
    """

    __tablename__ = "mistake_review_records"

    id = Column(String, primary_key=True)

    # 关联错题
    mistake_id = Column(
        String,
        ForeignKey("mistakes.id"),
        nullable=False,
        index=True,
    )

    # 关联用户
    user_id = Column(
        String,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # 本次复习完成后的状态
    status = Column(String, nullable=False)

    # 本次复习的具体时间
    reviewed_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    # 所属错题
    mistake = relationship(
        "Mistake",
        back_populates="review_records"
    )
