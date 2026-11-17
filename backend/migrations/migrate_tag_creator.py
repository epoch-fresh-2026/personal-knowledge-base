"""标签创建者字段迁移（Issue #51）。

为 tags 表增加 creator_id 列，记录全局共享标签的创建者。

兼容现有数据：历史标签没有创建者信息，creator_id 置 NULL（表示系统/未知来源）。
按 Issue 规则，历史无创建者的标签不受"仅创建者可删除"约束限制（无人可冒名删除），
如需管理可由数据维护侧自行补充 creator_id。

迁移为幂等操作，可重复执行；不改动已有列与其他表。
"""

from sqlalchemy import inspect, text

from shared.db import engine


def migrate():
    inspector = inspect(engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("tags")
    }

    with engine.begin() as conn:
        if "creator_id" not in columns:
            conn.execute(text(
                "ALTER TABLE tags ADD COLUMN creator_id VARCHAR"
            ))

    print("标签创建者字段迁移完成！")


if __name__ == "__main__":
    migrate()
