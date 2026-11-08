import json
import math
import re

import jieba
from sqlalchemy.orm import Session

from modules.ingest.domain.models import Chunk
from modules.retrieve.repository import chunk_repo
from shared.embedding import get_embedding


def tokenize(query: str) -> list[str]:
    """将查询文本拆分为关键词。"""
    words = jieba.lcut(query)

    stop_words = {
        "的", "了", "是", "在", "和", "与",
        "什么", "怎么", "为什么", "如何", "没有", "看到"
    }

    keywords = []

    for word in words:
        word = word.strip()

        if len(word) < 2:
            continue

        if word in stop_words:
            continue

        if re.fullmatch(r"[\W_]+", word):
            continue

        keywords.append(word)

    return list(dict.fromkeys(keywords))


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float]
) -> float:
    """计算两个向量的余弦相似度。"""
    if len(vector_a) != len(vector_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))

    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


async def search(
    db: Session,
    query: str,
    top_k: int = 5
) -> dict:
    """结合语义检索和关键词检索的混合检索。"""

    if not query or not query.strip():
        return {
            "query": query,
            "keywords": [],
            "results": []
        }

    keywords = tokenize(query)

    # 1. 关键词检索
    keyword_chunks = (
        chunk_repo.search_by_keywords(db, keywords, top_k=top_k * 3)
        if keywords else []
    )

    # 2. 语义检索
    semantic_scores = {}

    try:
        query_vector = await get_embedding(query)

        chunks = (
            db.query(Chunk)
            .filter(Chunk.embedding.isnot(None))
            .all()
        )

        semantic_candidates = []

        for chunk in chunks:
            try:
                chunk_vector = json.loads(chunk.embedding)

                if len(chunk_vector) != len(query_vector):
                    continue

                similarity = cosine_similarity(
                    query_vector,
                    chunk_vector
                )

                semantic_candidates.append(
                    (chunk, max(0.0, similarity))
                )

            except (ValueError, TypeError, json.JSONDecodeError):
                continue

        # 只保留语义相似度最高的 top_k * 3 个候选结果
        semantic_candidates.sort(
            key=lambda item: item[1],
            reverse=True
        )

        semantic_scores = {
            chunk.id: score
            for chunk, score in semantic_candidates[:top_k * 3]
        }

    except Exception as e:
        # Embedding 服务不可用时，保留关键词检索结果
        print(f"语义检索失败，降级到关键词检索：{e}")
        semantic_scores = {}

    # 3. 合并两路检索结果
    candidate_chunks = {}

    for chunk in keyword_chunks:
        candidate_chunks[chunk.id] = chunk

    if semantic_scores:
        semantic_chunks = (
            db.query(Chunk)
            .filter(Chunk.id.in_(semantic_scores.keys()))
            .all()
        )

        for chunk in semantic_chunks:
            candidate_chunks[chunk.id] = chunk

    # 4. 计算混合评分
    results = []

    for chunk in candidate_chunks.values():
        hit_count = sum(
            1 for keyword in keywords
            if keyword in chunk.content
        )

        keyword_score = (
            hit_count / len(keywords)
            if keywords else 0.0
        )

        semantic_score = semantic_scores.get(chunk.id, 0.0)

        if semantic_scores:
            hybrid_score = (
                0.7 * semantic_score
                + 0.3 * keyword_score
            )
        else:
            hybrid_score = keyword_score

        results.append({
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "content": chunk.content,
            "chunk_index": chunk.chunk_index,
            "semantic_score": semantic_score,
            "keyword_score": keyword_score,
            "retrieval_score": hybrid_score,
        })

    # 5. 按混合评分排序
    results.sort(
        key=lambda item: item["retrieval_score"],
        reverse=True
    )

    return {
        "query": query,
        "keywords": keywords,
        "results": results[:top_k]
    }