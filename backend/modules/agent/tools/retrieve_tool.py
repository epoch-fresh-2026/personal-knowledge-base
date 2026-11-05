from typing import Callable


async def retrieve(
    query: str,
    top_k: int,
    retrieve_func: Callable,
) -> dict:
    """
    Retrieve Tool：通过注入的接口调用检索能力。

    不直接依赖 Retrieve 业务模块，也不直接操作数据库。
    """
    return retrieve_func(query, top_k)