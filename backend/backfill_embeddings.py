import asyncio

from shared.db import SessionLocal
from modules.ingest.domain.models import Chunk
from modules.ingest.service.embedding_service import (
    generate_chunk_embeddings,
)


async def backfill_embeddings():
    """为历史上尚未生成向量的 Chunk 补全 Embedding。"""

    db = SessionLocal()

    try:
        chunks = (
            db.query(Chunk)
            .filter(Chunk.embedding.is_(None))
            .all()
        )

        if not chunks:
            print("所有 Chunk 都已经有向量，无需补全。")
            return

        print(f"发现 {len(chunks)} 个缺少向量的 Chunk。")

        await generate_chunk_embeddings(chunks)

        db.commit()

        print(f"成功为 {len(chunks)} 个 Chunk 生成向量。")

    except Exception as e:
        db.rollback()
        print(f"向量补全失败，数据库事务已回滚：{e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(backfill_embeddings())