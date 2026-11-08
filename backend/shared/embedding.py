import math

import httpx

from shared.config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
)


async def get_embedding(text: str) -> list[float]:
    """调用阿里云百炼 Embedding API，将文本转换为向量。"""

    if not EMBEDDING_API_KEY:
        raise ValueError(
            "未配置 EMBEDDING_API_KEY，请检查 backend/.env 文件"
        )

    if not text or not text.strip():
        raise ValueError("待向量化的文本不能为空")

    base_url = EMBEDDING_BASE_URL.removesuffix(
        "/compatible-mode/v1"
    ).rstrip("/")

    url = (
        f"{base_url}/api/v1/services/"
        "embeddings/text-embedding/text-embedding"
    )

    headers = {
        "Authorization": f"Bearer {EMBEDDING_API_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": EMBEDDING_MODEL,
        "input": text,
        "parameters": {
            "dimension": 1024
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            headers=headers,
            json=data,
        )

        if not response.is_success:
            try:
                error_detail = response.json()
            except ValueError:
                error_detail = response.text

            raise RuntimeError(
                f"Embedding API 请求失败（HTTP {response.status_code}）："
                f"{error_detail}"
            )

    try:
        result = response.json()
        vector = result["output"]["embeddings"][0]["embedding"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise RuntimeError(
            "Embedding API 返回的数据格式不正确"
        ) from e

    if not isinstance(vector, list) or len(vector) != 1024:
        raise RuntimeError(
            "Embedding API 返回的向量维度不正确，预期为 1024"
        )

    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in vector
    ):
        raise RuntimeError(
            "Embedding API 返回的向量包含无效数值"
        )

    return [float(value) for value in vector]