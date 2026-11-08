import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

# backend 目录
BASE_DIR = Path(__file__).resolve().parents[1]

# 固定读取 backend/.env
load_dotenv(BASE_DIR / ".env")

# 数据库配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pkb.db")

# SQLite 相对路径统一转换为 backend 目录下的绝对路径
database_url = make_url(DATABASE_URL)

if (
    database_url.drivername.startswith("sqlite")
    and database_url.database
    and database_url.database != ":memory:"
):
    db_path = Path(database_url.database)

    if not db_path.is_absolute():
        db_path = (BASE_DIR / db_path).resolve()
        database_url = database_url.set(database=str(db_path))

DATABASE_URL = database_url.render_as_string(hide_password=False)

# LLM 配置
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    "https://api.deepseek.com"
)

# Embedding 配置
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_BASE_URL = os.getenv(
    "EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "text-embedding-v3"
)