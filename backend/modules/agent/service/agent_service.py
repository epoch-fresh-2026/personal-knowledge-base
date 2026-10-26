from sqlalchemy.orm import Session
from modules.retrieve.service.search import search
from shared.llm import chat_completion

async def rewrite_query(original_query: str) -> str:
    """
    Agent 工作流：把口语化问题改写成专业检索词
    """
    prompt = f"请将以下用户问题改写为适合搜索引擎检索的专业关键词，只输出改写后的词，不要解释：\n{original_query}"
    try:
        rewritten = await chat_completion(prompt)
        return rewritten.strip()
    except Exception:
        return original_query

async def ask_question(db: Session, question: str, top_k: int = 3) -> dict:
    """
    Agent 核心编排：改写 -> 检索 -> 生成 -> 溯源
    """
    # 1. Agent 决定是否改写
    rewritten_query = await rewrite_query(question)

    # 2. 调度 retrieve 模块
    search_result = search(db, rewritten_query, top_k=top_k)
    chunks = search_result.get("results", [])

    # 3. 严格防幻觉拦截：如果检索结果为空，直接返回，不调用 LLM
    if not chunks:
        return {
            "answer": "抱歉，知识库中没有找到与您问题相关的内容，我无法回答。",
            "sources": [],
            "rewritten_query": rewritten_query
        }

    # 4. 拼装 Prompt
    context_text = ""
    for i, chunk in enumerate(chunks):
        context_text += f"[{i + 1}] {chunk['content']}\n\n"

    prompt = f"""你是一个个人知识库助手。请严格根据下面提供的资料回答用户的问题。
如果资料中不包含答案，请直接回答"根据已有资料，我无法回答该问题"，不要编造。
回答时请尽量精简，并在答案末尾用 [1]、[2] 的形式标注引用了哪几条资料。

资料：
{context_text}

用户问题：{question}
"""

    # 5. 调用 LLM 生成答案
    answer = await chat_completion(prompt)

    # 6. 拦截大模型的“拒答”情况（解决前端展示了无关参考来源的 bug）
    if "无法回答" in answer or "未找到" in answer or "资料库中未找到" in answer:
        return {
            "answer": answer,
            "sources": [],  # 👈 强制清空无关的溯源信息
            "rewritten_query": rewritten_query
        }

    # 7. 正常回答，提取溯源信息
    sources = [
        {
            "chunk_id": c["chunk_id"],
            "document_id": c["document_id"],
            "content": c["content"],
        }
        for c in chunks
    ]

    return {
        "answer": answer,
        "sources": sources,
        "rewritten_query": rewritten_query
    }