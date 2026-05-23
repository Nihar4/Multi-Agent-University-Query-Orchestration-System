"""Chat endpoint — entry point into the multi-agent orchestrator."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agents.orchestrator import handle_question
from ..database import get_db
from ..models import ChatMessage, Student
from ..schemas import ChatMessageOut, ChatRequest, ChatResponse
from ..security import get_current_student

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def post_chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current: Student = Depends(get_current_student),
):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")
    try:
        result = handle_question(db, current, payload.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ChatResponse(
        answer=result.answer,
        routed_to=result.routed_to,
        ticket_ids=result.ticket_ids,
        trace=result.trace,
    )


@router.get("/history", response_model=list[ChatMessageOut])
def get_history(
    db: Session = Depends(get_db),
    current: Student = Depends(get_current_student),
    limit: int = 50,
):
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.student_id == current.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    return rows
