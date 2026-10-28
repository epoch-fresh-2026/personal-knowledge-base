from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.db import get_db
from modules.ingest.domain.models import Mistake

router = APIRouter(prefix="/mistakes", tags=["mistakes"])


class MistakeCreate(BaseModel):
    question: str
    correct_answer: str = ""
    wrong_answer: str = ""
    error_reason: str = ""
    knowledge_points: str = ""


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
        status="unreviewed",
    )
    db.add(mistake)
    db.commit()
    db.refresh(mistake)

    return {"id": mistake.id, "message": "错题添加成功"}


@router.get("")
def list_mistakes(
    user_id: str = Query("u_zhangsan"),
    db: Session = Depends(get_db),
):
    mistakes = (
        db.query(Mistake)
        .filter(Mistake.user_id == user_id)
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
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in mistakes
    ]