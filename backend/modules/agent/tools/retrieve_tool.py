import inspect
from collections.abc import Callable
from typing import Any


async def retrieve(
    query: str,
    top_k: int,
    retrieve_func: Callable[[str, int], Any],
) -> dict[str, Any]:
    """
    Retrieve Tool：
    通过注入的接口调用检索能力。

    同时兼容同步和异步检索函数。
    """

    result = retrieve_func(query, top_k)

    if inspect.isawaitable(result):
        result = await result

    return result