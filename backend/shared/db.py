from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import DATABASE_URL

# SQLite 需要 check_same_thread=False，允许多线程访问
connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)

Base = declarative_base()


def init_db():
    """初始化数据库表，并创建默认测试用户。"""

    # 导入模型，让 Base 知道有哪些表
    from modules.ingest.domain import models
    from modules.manage.domain import models as manage_models
    from modules.ingest.domain.models import User

    Base.metadata.create_all(bind=engine)

    # 初始化虚拟用户，方便测试社交功能
    db = SessionLocal()

    try:
        if db.query(User).count() == 0:
            u1 = User(
                id="u_zhangsan",
                nickname="张三",
                avatar="🧑‍💻"
            )

            u2 = User(
                id="u_lisi",
                nickname="李四",
                avatar="👩‍💻"
            )

            db.add_all([u1, u2])
            db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_db():
    """FastAPI 依赖：每个请求一个 session。"""

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()