"""文档软删除字段迁移（Issue #47）。

为 documents 表增加：
- is_deleted: BOOLEAN，软删除标记，默认 False；
- deleted_at: DATETIME，删除时间，默认 NULL。

兼容现有数据：所有已存在文档保持 is_deleted=False（未删除）。
迁移为幂等操作，可重复执行。
"""

from sqlalchemy import inspect, text

from shared.db import engine


def migrate():
    inspector = inspect(engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("documents")
    }

    with engine.begin() as conn:
        if "is_deleted" not in columns:
            conn.execute(text(
                "ALTER TABLE documents "
                "ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"
            ))

        if "deleted_at" not in columns:
            conn.execute(text(
                "ALTER TABLE documents ADD COLUMN deleted_at DATETIME"
            ))

    print("文档软删除字段迁移完成！")


if __name__ == "__main__":
    migrate()
