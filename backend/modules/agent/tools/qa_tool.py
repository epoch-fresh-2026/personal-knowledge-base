from shared.llm import chat_completion


async def generate_answer(question: str, chunks: list[dict]) -> str:
    """
    QA Tool：根据检索到的知识生成答案。
    """

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

    return await chat_completion(prompt)