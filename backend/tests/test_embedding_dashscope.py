import asyncio
import os

import pytest

from shared.config import EMBEDDING_API_KEY
from shared.embedding import get_embedding


@pytest.mark.skipif(
    os.getenv("RUN_DASHSCOPE_TEST") != "1",
    reason="在线 API 测试，需要手动设置 RUN_DASHSCOPE_TEST=1"
)
def test_embedding():
    """真实测试阿里云百炼 Embedding API。"""

    if not EMBEDDING_API_KEY:
        pytest.fail("未配置 EMBEDDING_API_KEY")

    vector = asyncio.run(
        get_embedding("个人知识库系统的向量检索测试")
    )

    assert isinstance(vector, list)
    assert len(vector) == 1024
    assert all(isinstance(value, float) for value in vector)

    print(f"\n向量维度：{len(vector)}")
    print(f"前五个数值：{vector[:5]}")