import asyncio

from modules.agent.service import agent_service


# 模拟知识库中的一条资料
TEST_CHUNK = {
    "chunk_id": "chunk-001",
    "document_id": "doc-001",
    "content": "LFUCache 初始化了 capacity、cache 和 freq 三个成员。",
    "chunk_index": 0,
}


def test_agent_normal_flow(monkeypatch):
    """测试正常问答、多路检索和结果去重。"""

    async def fake_chat_completion(prompt):
        return "LFUCache 初始化成员"

    async def fake_generate_answer(question, chunks):
        return "LFUCache 初始化了三个成员。[1]"

    monkeypatch.setattr(
        agent_service,
        "chat_completion",
        fake_chat_completion
    )

    monkeypatch.setattr(
        agent_service,
        "generate_answer",
        fake_generate_answer
    )

    retrieve_calls = []

    def fake_retrieve(query, top_k):
        retrieve_calls.append(query)

        return {
            "keywords": ["LFUCache"],
            "results": [TEST_CHUNK],
        }

    result = asyncio.run(
        agent_service.agent_chat(
            "LFUCache 初始化了什么？",
            3,
            fake_retrieve
        )
    )

    assert "三个成员" in result["answer"]

    # 原始问题和改写问题都执行了检索
    assert len(retrieve_calls) == 2

    # 相同资料只保留一份
    assert len(result["sources"]) == 1

    assert result["sources"][0]["chunk_id"] == "chunk-001"

    actions = [step["action"] for step in result["steps"]]

    assert "rewrite_query" in actions
    assert "retrieve" in actions
    assert "evaluate" in actions
    assert "qa" in actions


def test_agent_retry_success(monkeypatch):
    """测试第一次检索失败，第二次检索成功。"""

    async def fake_chat_completion(prompt):
        if "上一次使用的检索词" in prompt:
            return "LFUCache 初始化成员"

        return "LFUCache"

    async def fake_generate_answer(question, chunks):
        return "找到了相关资料。[1]"

    monkeypatch.setattr(
        agent_service,
        "chat_completion",
        fake_chat_completion
    )

    monkeypatch.setattr(
        agent_service,
        "generate_answer",
        fake_generate_answer
    )

    retrieve_count = 0

    def fake_retrieve(query, top_k):
        nonlocal retrieve_count
        retrieve_count += 1

        # 前两次检索为空，第三次找到资料
        if retrieve_count < 3:
            return {
                "keywords": [],
                "results": [],
            }

        return {
            "keywords": ["LFUCache"],
            "results": [TEST_CHUNK],
        }

    result = asyncio.run(
        agent_service.agent_chat(
            "LFUCache 初始化了什么？",
            3,
            fake_retrieve
        )
    )

    assert retrieve_count == 3
    assert len(result["sources"]) == 1
    assert "找到了相关资料" in result["answer"]

    # 第二轮检索成功后，工作流正常进入 QA
    actions = [step["action"] for step in result["steps"]]

    assert "refine_query" in actions
    assert actions.count("evaluate") == 2
    assert "qa" in actions

    # 检查最大步骤数限制
    assert len(result["steps"]) <= agent_service.MAX_WORKFLOW_STEPS


def test_agent_retry_failure(monkeypatch):
    """测试两轮检索都失败时，Agent 正确拒绝回答。"""

    async def fake_chat_completion(prompt):
        if "上一次使用的检索词" in prompt:
            return "调整后的检索词"

        return "测试关键词"

    async def fake_generate_answer(question, chunks):
        raise AssertionError("检索结果不足，不应该调用 QA")

    monkeypatch.setattr(
        agent_service,
        "chat_completion",
        fake_chat_completion
    )

    monkeypatch.setattr(
        agent_service,
        "generate_answer",
        fake_generate_answer
    )

    retrieve_count = 0

    def fake_retrieve(query, top_k):
        nonlocal retrieve_count
        retrieve_count += 1

        return {
            "keywords": [],
            "results": [],
        }

    result = asyncio.run(
        agent_service.agent_chat(
            "知识库中没有的内容",
            3,
            fake_retrieve
        )
    )

    assert retrieve_count == 3
    assert result["sources"] == []
    assert "无法可靠地回答" in result["answer"]

    actions = [step["action"] for step in result["steps"]]

    assert "refine_query" in actions
    assert actions.count("evaluate") == 2
    assert "qa" not in actions

    assert len(result["steps"]) <= agent_service.MAX_WORKFLOW_STEPS