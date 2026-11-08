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

def test_merge_results_ranking_and_filtering():
    """测试综合评分、排序和低相关度资料过滤。"""

    low_chunk = {
        "chunk_id": "chunk-low",
        "document_id": "doc-001",
        "content": "LFUCache 是一种缓存结构。",
        "chunk_index": 0,
    }

    high_chunk = {
        "chunk_id": "chunk-high",
        "document_id": "doc-002",
        "content": "LFUCache 使用 capacity 和 cache 管理缓存。",
        "chunk_index": 0,
    }

    irrelevant_chunk = {
        "chunk_id": "chunk-irrelevant",
        "document_id": "doc-003",
        "content": "这是一段无关内容。",
        "chunk_index": 0,
    }

    search_results = [
        {
            "keywords": ["LFUCache", "capacity", "cache"],
            "results": [
                low_chunk,
                high_chunk,
                irrelevant_chunk,
            ],
        }
    ]

    results = agent_service.merge_results(search_results, 5)

    # 高覆盖率资料应该排在前面
    assert results[0]["chunk_id"] == "chunk-high"
    assert results[1]["chunk_id"] == "chunk-low"

    # 低相关度资料应该被过滤
    assert all(
        item["chunk_id"] != "chunk-irrelevant"
        for item in results
    )

    # 综合评分应包含覆盖率和排名因素
    assert results[0]["_agent_score"] > results[1]["_agent_score"]


def test_merge_results_duplicate_uses_best_score():
    """测试多路检索出现重复资料时保留最高评分。"""

    chunk = {
        "chunk_id": "chunk-001",
        "document_id": "doc-001",
        "content": "LFUCache 使用 capacity 和 cache。",
        "chunk_index": 0,
    }

    search_results = [
        {
            "keywords": ["LFUCache", "capacity", "cache"],
            "results": [chunk],
        },
        {
            "keywords": ["LFUCache"],
            "results": [chunk],
        },
    ]

    results = agent_service.merge_results(search_results, 5)

    assert len(results) == 1
    assert results[0]["chunk_id"] == "chunk-001"

    # 第二路检索的关键词完全命中，应该保留更高评分
    assert results[0]["_agent_score"] == 1.0


def test_is_sufficient_threshold():
    """测试检索结果充分性判断阈值。"""

    assert agent_service.is_sufficient([
        {"_agent_score": 0.5}
    ])

    assert not agent_service.is_sufficient([
        {"_agent_score": 0.49}
    ])

    assert not agent_service.is_sufficient([])

def test_agent_retry_invalid_result(monkeypatch):
    """测试第二轮检索返回异常数据时，Agent 能正常处理。"""

    async def fake_chat_completion(prompt):
        if "上一次使用的检索词" in prompt:
            return "调整后的检索词"

        return "测试关键词"

    async def fake_generate_answer(question, chunks):
        raise AssertionError("检索结果无效，不应该调用 QA")

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

        if retrieve_count < 3:
            return {
                "keywords": [],
                "results": [],
            }

        # 模拟检索工具返回异常数据
        return None

    result = asyncio.run(
        agent_service.agent_chat(
            "测试异常检索",
            3,
            fake_retrieve
        )
    )

    assert retrieve_count == 3
    assert result["sources"] == []
    assert "无法可靠地回答" in result["answer"]
    assert "qa" not in [
        step["action"] for step in result["steps"]
    ]

def test_merge_results_invalid_fields():
    """测试检索结果内部字段异常时能够安全跳过。"""

    valid_result = {
        "keywords": ["LFUCache"],
        "results": [TEST_CHUNK],
    }

    invalid_result = {
        "keywords": None,
        "results": None,
    }

    results = agent_service.merge_results(
        [invalid_result, valid_result],
        5
    )

    assert len(results) == 1
    assert results[0]["chunk_id"] == "chunk-001"