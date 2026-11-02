from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from shared.db import Base

class FavoriteDocument(Base):
    __tablename__ = "favorite_documents"
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    document_id = Column(String, ForeignKey("documents.id"), primary_key=True)
    
class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    nickname = Column(String, nullable=False)
    avatar = Column(String, default="👤")

class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    is_public = Column(Boolean, default=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    owner = relationship("User")

class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Text, nullable=True)
    chunk_index = Column(Integer, nullable=False)

    document = relationship("Document", back_populates="chunks")

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