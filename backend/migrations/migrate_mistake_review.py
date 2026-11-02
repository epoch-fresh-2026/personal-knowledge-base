from sqlalchemy import inspect, text

from shared.db import engine


def migrate():
    inspector = inspect(engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("mistakes")
    }

    with engine.begin() as conn:
        # 增加复习次数
        if "review_count" not in columns:
            conn.execute(text(
                "ALTER TABLE mistakes "
                "ADD COLUMN review_count INTEGER NOT NULL DEFAULT 0"
            ))

        # 增加最近复习时间
        if "last_reviewed_at" not in columns:
            conn.execute(text(
                "ALTER TABLE mistakes "
                "ADD COLUMN last_reviewed_at DATETIME"
            ))

        # 转换旧复习状态
        conn.execute(text("""
            UPDATE mistakes
            SET status = CASE
                WHEN status = 'unreviewed' THEN 'pending'
                WHEN status = 'reviewed' THEN 'reviewing'
                ELSE status
            END
        """))

    print("错题复习数据库迁移完成！")


if __name__ == "__main__":
    migrate()