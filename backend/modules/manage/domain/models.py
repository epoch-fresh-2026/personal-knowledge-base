from sqlalchemy import Column, String, ForeignKey, Boolean
from shared.db import Base

class Folder(Base):
    __tablename__ = "folders"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True) # 👈 新增：文件夹所属人
    is_public = Column(Boolean, default=False) # 👈 新增：文件夹是否公开

class DocumentFolder(Base):
    __tablename__ = "document_folders"
    document_id = Column(String, ForeignKey("documents.id"), primary_key=True)
    folder_id = Column(String, ForeignKey("folders.id"), primary_key=True)

class FavoriteFolder(Base):
    __tablename__ = "favorite_folders"
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    folder_id = Column(String, ForeignKey("folders.id"), primary_key=True)