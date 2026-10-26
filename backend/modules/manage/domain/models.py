from sqlalchemy import Column, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship # 👈 必须引入这个
from shared.db import Base

class Folder(Base):
    __tablename__ = "folders"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True) 
    is_public = Column(Boolean, default=False)
    
    # 👇 加上这一行！建立与 User 表的关联
    owner = relationship("User")

class DocumentFolder(Base):
    __tablename__ = "document_folders"
    document_id = Column(String, ForeignKey("documents.id"), primary_key=True)
    folder_id = Column(String, ForeignKey("folders.id"), primary_key=True)

class FavoriteFolder(Base):
    __tablename__ = "favorite_folders"
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    folder_id = Column(String, ForeignKey("folders.id"), primary_key=True)