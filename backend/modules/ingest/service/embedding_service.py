import json

from modules.ingest.domain.models import Chunk
from shared.embedding import get_embedding


async def generate_chunk_embeddings(
    chunks: list[Chunk],
) -> None:
    """
    为一组 Chunk 生成 Embedding 向量，
    并将向量以 JSON 格式保存到 embedding 字段。
    """

    for chunk in chunks:
        if not chunk.content or not chunk.content.strip():
            raise ValueError(f"Chunk 内容不能为空：{chunk.id}")

        vector = await get_embedding(chunk.content)

        if len(vector) != 1024:
            raise ValueError(
                f"Embedding 维度错误：预期 1024，实际 {len(vector)}"
            )

        chunk.embedding = json.dumps(
            vector,
            ensure_ascii=False,
        )