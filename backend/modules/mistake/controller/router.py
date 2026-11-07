from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.db import get_db
from modules.ingest.domain.models import Mistake
from modules.mistake.service.recommendation_service import (
    get_review_recommendations
)
from modules.mistake.service.knowledge_point_service import (
    get_knowledge_point_statistics
)

router = APIRouter(prefix="/mistakes", tags=["mistakes"])


class MistakeCreate(BaseModel):
    question: str
    correct_answer: str = ""
    wrong_answer: str = ""
    error_reason: str = ""
    knowledge_points: str = ""

class MistakeUpdate(BaseModel):
    question: str
    correct_answer: str = ""
    wrong_answer: str = ""
    error_reason: str = ""
    knowledge_points: str = ""

class MistakeReviewComplete(BaseModel):
    status: str = "reviewing"

@router.post("")
def create_mistake(
    req: MistakeCreate,
    user_id: str = Query("u_zhangsan"),
    db: Session = Depends(get_db),
):
    mistake = Mistake(
        id=str(uuid4()),
        user_id=user_id,
        question=req.question,
        correct_answer=req.correct_answer,
        wrong_answer=req.wrong_answer,
        error_reason=req.error_reason,
        knowledge_points=req.knowledge_points,
        status="pending",
        review_count=0,
        last_reviewed_at=None,
    )
    db.add(mistake)
    db.commit()
    db.refresh(mistake)

    return {"id": mistake.id, "message": "错题添加成功"}


@router.get("")
def list_mistakes(
    user_id: str = Query("u_zhangsan"),
    status: str = Query(None),
    db: Session = Depends(get_db),
):
    mistakes_query = db.query(Mistake).filter(
        Mistake.user_id == user_id
    )

    if status:
        if status not in ("pending", "reviewing", "mastered"):
            return {"message": "无效的复习状态"}
        mistakes_query = mistakes_query.filter(Mistake.status == status)

    mistakes = (
        mistakes_query
        .order_by(Mistake.created_at.desc())
        .all()
    )

    return [
        {
            "id": item.id,
            "question": item.question,
            "correct_answer": item.correct_answer,
            "wrong_answer": item.wrong_answer,
            "error_reason": item.error_reason,
            "knowledge_points": item.knowledge_points,
            "status": item.status,
            "review_count": item.review_count,
            "last_reviewed_at": (
                item.last_reviewed_at.isoformat()
                if item.last_reviewed_at else None
            ),
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in mistakes
    ]

@router.get("/knowledge-points")
def list_knowledge_point_statistics(
    user_id: str = Query("u_zhangsan"),
    db: Session = Depends(get_db),
):
    """
    获取当前用户的知识点掌握情况统计。
    """
    return get_knowledge_point_statistics(db, user_id)

class MistakeStatusUpdate(BaseModel):
    status: str


@router.patch("/{mistake_id}/status")
def update_mistake_status(
    mistake_id: str,
    req: MistakeStatusUpdate,
    user_id: str = Query("u_zhangsan"),
    db: Session = Depends(get_db),
):
    if req.status not in ("pending", "reviewing", "mastered"):
        return {"message": "无效的复习状态"}

    mistake = (
        db.query(Mistake)
        .filter(
            Mistake.id == mistake_id,
            Mistake.user_id == user_id,
        )
        .first()
    )

    if mistake is None:
        return {"message": "未找到错题"}

    mistake.status = req.status
    db.commit()
    db.refresh(mistake)

    return {
        "id": mistake.id,
        "status": mistake.status,
        "message": "复习状态更新成功",
    }

@router.post("/{mistake_id}/review")
def complete_mistake_review(
    mistake_id: str,
    req: MistakeReviewComplete,
    user_id: str = Query("u_zhangsan"),
    db: Session = Depends(get_db),
):
    if req.status not in ("pending", "reviewing", "mastered"):
        return {"message": "无效的复习状态"}

    mistake = (
        db.query(Mistake)
        .filter(
            Mistake.id == mistake_id,
            Mistake.user_id == user_id,
        )
        .first()
    )

    if mistake is None:
        return {"message": "未找到错题"}

    mistake.status = req.status
    mistake.review_count = (mistake.review_count or 0) + 1
    mistake.last_reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(mistake)

    return {
        "id": mistake.id,
        "status": mistake.status,
        "review_count": mistake.review_count,
        "last_reviewed_at": (
            mistake.last_reviewed_at.isoformat()
            if mistake.last_reviewed_at else None
        ),
        "message": "复习记录成功",
    }

@router.put("/{mistake_id}")
def update_mistake(
    mistake_id: str,
    req: MistakeUpdate,
    user_id: str = Query("u_zhangsan"),
    db: Session = Depends(get_db),
):
    mistake = (
        db.query(Mistake)
        .filter(
            Mistake.id == mistake_id,
            Mistake.user_id == user_id,
        )
        .first()
    )

    if mistake is None:
        return {"message": "未找到错题"}

    mistake.question = req.question
    mistake.correct_answer = req.correct_answer
    mistake.wrong_answer = req.wrong_answer
    mistake.error_reason = req.error_reason
    mistake.knowledge_points = req.knowledge_points

    db.commit()
    db.refresh(mistake)

    return {
        "id": mistake.id,
        "message": "错题更新成功",
    }


@router.delete("/{mistake_id}")
def delete_mistake(
    mistake_id: str,
    user_id: str = Query("u_zhangsan"),
    db: Session = Depends(get_db),
):
    mistake = (
        db.query(Mistake)
        .filter(
            Mistake.id == mistake_id,
            Mistake.user_id == user_id,
        )
        .first()
    )

    if mistake is None:
        return {"message": "未找到错题"}

    db.delete(mistake)
    db.commit()

    return {
        "id": mistake_id,
        "message": "错题删除成功",
    }

@router.get("/recommendations")
def list_review_recommendations(
    user_id: str = Query("u_zhangsan"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """
    获取当前用户的个性化复习建议。
    """
    return get_review_recommendations(
        db,
        user_id,
        limit
    )