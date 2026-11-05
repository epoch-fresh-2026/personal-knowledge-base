from collections.abc import Callable
from typing import Any

from modules.agent.tools.retrieve_tool import retrieve
from modules.agent.tools.qa_tool import generate_answer
from shared.llm import chat_completion


# 最多进行两轮检索：
# 第一轮：原始问题 + 改写问题
# 第二轮：调整后的查询
MAX_RETRIEVAL_ROUNDS = 2

# 工作流最大步骤数，防止无限执行
MAX_WORKFLOW_STEPS = 8


def record_step(
    steps: list[dict],
    action: str,
    status: str,
    **details: Any
) -> None:
    """记录 Agent 执行步骤。"""

    if len(steps) >= MAX_WORKFLOW_STEPS:
        return

    step = {
        "step": len(steps) + 1,
        "action": action,
        "status": status,
    }

    step.update(details)
    steps.append(step)


async def rewrite_query(original_query: str) -> str:
    """将用户问题改写为适合检索的关键词。"""

    prompt = f"""请将以下用户问题改写为适合知识库检索的关键词或短句。
保留问题中的核心概念，只输出改写结果，不要解释。

用户问题：
{original_query}
"""

    try:
        result = await chat_completion(prompt)
        return result.strip() or original_query
    except Exception:
        return original_query


async def refine_query(
    original_query: str,
    previous_query: str
) -> str:
    """首次检索效果不足时，调整检索查询。"""

    prompt = f"""你是一个知识库检索助手。

用户原始问题：
{original_query}

上一次使用的检索词：
{previous_query}

请重新组织检索关键词，尽量使用不同但相关的表达，
帮助知识库找到更相关的资料。

只输出新的检索关键词，不要解释。
"""

    try:
        result = await chat_completion(prompt)
        return result.strip() or original_query
    except Exception:
        return original_query


def merge_results(
    search_results: list[dict],
    top_k: int
) -> list[dict]:
    """合并多路检索结果，根据关键词覆盖率重新排序。"""

    merged = {}

    for search_result in search_results:
        keywords = list(set(search_result.get("keywords", [])))

        for chunk in search_result.get("results", []):
            chunk_id = chunk.get("chunk_id")

            if not chunk_id:
                continue

            content = chunk.get("content", "")
            hit_count = sum(
                1 for keyword in keywords
                if keyword and keyword in content
            )

            score = (
                hit_count / len(keywords)
                if keywords else 0
            )

            if chunk_id not in merged:
                merged[chunk_id] = {
                    **chunk,
                    "_agent_score": score,
                    "_agent_hits": hit_count,
                }
            else:
                # 同一资料在不同检索路径中出现时，
                # 保留表现更好的匹配分数。
                merged[chunk_id]["_agent_score"] = max(
                    merged[chunk_id]["_agent_score"],
                    score
                )

                merged[chunk_id]["_agent_hits"] = max(
                    merged[chunk_id]["_agent_hits"],
                    hit_count
                )

    results = list(merged.values())

    results.sort(
        key=lambda item: (
            item["_agent_score"],
            item["_agent_hits"]
        ),
        reverse=True
    )

    return results[:top_k]


def is_sufficient(chunks: list[dict]) -> bool:
    """判断检索结果是否足以进入回答阶段。"""

    if not chunks:
        return False

    best_score = chunks[0].get("_agent_score", 0)

    # 最高关键词覆盖率达到 50%，认为检索结果初步合格。
    return best_score >= 0.5


def remove_internal_fields(chunks: list[dict]) -> list[dict]:
    """移除 Agent 内部评分字段。"""

    return [
        {
            key: value
            for key, value in chunk.items()
            if not key.startswith("_agent_")
        }
        for chunk in chunks
    ]


def build_sources(chunks: list[dict]) -> list[dict]:
    """提取资料溯源信息。"""

    return [
        {
            "chunk_id": chunk["chunk_id"],
            "document_id": chunk["document_id"],
            "content": chunk["content"],
        }
        for chunk in chunks
    ]


async def agent_chat(
    question: str,
    top_k: int,
    retrieve_func: Callable[[str, int], dict]
) -> dict:
    """
    Agent 智能问答入口。

    工作流程：
    查询改写
    -> 多路检索
    -> 结果合并与筛选
    -> 判断是否足够
    -> 必要时再次检索
    -> QA 生成
    -> 资料溯源

    Agent 不直接操作数据库，通过 Tools 调用其他模块。
    """

    steps = []

    top_k = max(1, min(top_k, 10))

    # ==================== 1. 查询改写 ====================

    rewritten_query = await rewrite_query(question)

    record_step(
        steps,
        "rewrite_query",
        "success",
        original_query=question,
        rewritten_query=rewritten_query
    )

    # ==================== 2. 多路检索 ====================

    search_results = []

    # 第一轮：原始问题和改写问题分别检索
    initial_queries = list(dict.fromkeys([
        question,
        rewritten_query
    ]))

    for query in initial_queries:

        if len(steps) >= MAX_WORKFLOW_STEPS:
            break

        try:
            result = await retrieve(
                query,
                top_k,
                retrieve_func
            )

            if not isinstance(result, dict):
                result = {}

            search_results.append(result)

            record_step(
                steps,
                "retrieve",
                "success",
                round=1,
                query=query,
                result_count=len(result.get("results", []))
            )

        except Exception as e:
            record_step(
                steps,
                "retrieve",
                "failed",
                round=1,
                query=query,
                error=str(e)
            )

    # ==================== 3. 合并与筛选 ====================

    chunks = merge_results(search_results, top_k)

    sufficient = is_sufficient(chunks)

    record_step(
        steps,
        "evaluate",
        "success",
        round=1,
        result_count=len(chunks),
        sufficient=sufficient
    )

    # ==================== 4. 必要时再次检索 ====================

    if not sufficient and MAX_RETRIEVAL_ROUNDS > 1:

        retry_query = await refine_query(
            question,
            rewritten_query
        )

        rewritten_query = retry_query

        record_step(
            steps,
            "refine_query",
            "success",
            retry_query=retry_query
        )

        try:
            retry_result = await retrieve(
                retry_query,
                top_k,
                retrieve_func
            )

            search_results.append(retry_result)

            record_step(
                steps,
                "retrieve",
                "success",
                round=2,
                query=retry_query,
                result_count=len(
                    retry_result.get("results", [])
                )
            )

        except Exception as e:
            record_step(
                steps,
                "retrieve",
                "failed",
                round=2,
                query=retry_query,
                error=str(e)
            )

        # 合并第二轮检索结果
        chunks = merge_results(search_results, top_k)

        sufficient = is_sufficient(chunks)

        record_step(
            steps,
            "evaluate",
            "success",
            round=2,
            result_count=len(chunks),
            sufficient=sufficient
        )

    # ==================== 5. 检索结果不足 ====================

    if not sufficient:
        return {
            "answer": "抱歉，根据现有知识库资料，我无法可靠地回答该问题。",
            "sources": [],
            "rewritten_query": rewritten_query,
            "steps": steps
        }

    # ==================== 6. QA 生成 ====================

    clean_chunks = remove_internal_fields(chunks)

    try:
        answer = await generate_answer(
            question,
            clean_chunks
        )

        record_step(
            steps,
            "qa",
            "success"
        )

    except Exception as e:
        record_step(
            steps,
            "qa",
            "failed",
            error=str(e)
        )

        return {
            "answer": "抱歉，生成回答时出现问题，请稍后重试。",
            "sources": [],
            "rewritten_query": rewritten_query,
            "steps": steps
        }

    # ==================== 7. 防幻觉与溯源 ====================

    refusal_keywords = [
        "无法回答",
        "无法根据已有资料",
        "未找到",
        "不包含答案"
    ]

    if any(keyword in answer for keyword in refusal_keywords):
        sources = []
    else:
        sources = build_sources(clean_chunks)

    return {
        "answer": answer,
        "sources": sources,
        "rewritten_query": rewritten_query,
        "steps": steps
    }