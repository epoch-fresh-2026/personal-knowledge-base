import re
import jieba
from sqlalchemy.orm import Session
from modules.ingest.domain.models import Chunk
from modules.retrieve.repository import chunk_repo


def tokenize(query: str) -> list[str]:
    words = jieba.lcut(query)
    stop_words = {"的", "了", "是", "在", "和", "与", "什么", "怎么", "为什么", "如何", "没有", "看到"}
    keywords = []
    for w in words:
        w = w.strip()
        if len(w) < 2:
            continue
        if w in stop_words:
            continue
        if re.fullmatch(r"[\W_]+", w):  # 纯标点
            continue
        keywords.append(w)
    return keywords


def search(db: Session, query: str, top_k: int = 5) -> dict:
    keywords = tokenize(query)

    if not keywords:
        return {"query": query, "keywords": [], "results": []}

    chunks = chunk_repo.search_by_keywords(db, keywords, top_k=top_k)

    # 👇 新增：在 Python 端进行一次精确打分过滤
    results = []
    for c in chunks:
        # 统计这个 chunk 命中了多少个关键词
        hit_count = sum(1 for kw in keywords if kw in c.content)
        
        # 如果查询词很多（比如超过2个），要求必须命中至少 2 个词才算有效，过滤掉只是碰巧包含一个词的噪声
        if len(keywords) >= 2 and hit_count < 2:
            continue
            
        results.append({
            "chunk_id": c.id,
            "document_id": c.document_id,
            "content": c.content,
            "chunk_index": c.chunk_index,
        })

    # 如果因为过滤太严格导致全空了，做个兜底（全不返回）
    return {
        "query": query,
        "keywords": keywords,
        "results": results[:top_k],
    }