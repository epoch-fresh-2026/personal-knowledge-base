import asyncio

from shared import embedding


def test_get_embedding(monkeypatch):
    """测试 Embedding API 请求和向量解析，不调用真实网络。"""

    # 使用虚拟 API Key，不依赖 CI 环境中的真实密钥
    monkeypatch.setattr(
        embedding,
        "EMBEDDING_API_KEY",
        "test-api-key",
    )

    expected_vector = [0.1] * 1024

    class FakeResponse:
        is_success = True

        def json(self):
            return {
                "output": {
                    "embeddings": [
                        {
                            "embedding": expected_vector
                        }
                    ]
                }
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, headers, json):
            assert url.endswith(
                "/api/v1/services/embeddings/text-embedding/text-embedding"
            )
            assert headers["Authorization"] == "Bearer test-api-key"
            assert json["input"] == "个人知识库系统的向量检索测试"
            assert json["parameters"]["dimension"] == 1024

            return FakeResponse()

    monkeypatch.setattr(
        embedding.httpx,
        "AsyncClient",
        FakeAsyncClient,
    )

    vector = asyncio.run(
        embedding.get_embedding("个人知识库系统的向量检索测试")
    )

    assert isinstance(vector, list)
    assert len(vector) == 1024
    assert all(isinstance(value, float) for value in vector)