"""Ticket endpoints — list, detail, reply."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Student, Ticket, TicketMessage
from ..schemas import TicketListItem, TicketMessageOut, TicketOut, TicketReplyRequest
from ..security import get_current_student

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketListItem])
def list_tickets(
    db: Session = Depends(get_db),
    current: Student = Depends(get_current_student),
):
    rows = (
        db.query(Ticket)
        .filter(Ticket.student_id == current.id)
        .order_by(Ticket.created_at.desc())
        .all()
    )
    return [
        TicketListItem(
            id=t.id,
            subject=t.subject,
            status=t.status,
            department=t.department.name,
            department_code=t.department.code,
            created_at=t.created_at,
        )
        for t in rows
    ]


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current: Student = Depends(get_current_student),
):
    t = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.student_id == current.id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return TicketOut(
        id=t.id,
        subject=t.subject,
        summary=t.summary,
        original_question=t.original_question,
        status=t.status,
        department=t.department.name,
        department_code=t.department.code,
        created_at=t.created_at,
        updated_at=t.updated_at,
        messages=[
            TicketMessageOut(id=m.id, sender=m.sender, body=m.body, created_at=m.created_at)
            for m in t.messages
        ],
    )


@router.post("/{ticket_id}/reply", response_model=TicketMessageOut)
def reply_to_ticket(
    ticket_id: int,
    payload: TicketReplyRequest,
    db: Session = Depends(get_db),
    current: Student = Depends(get_current_student),
):
    t = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.student_id == current.id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    msg = TicketMessage(ticket_id=t.id, sender="student", body=payload.body)
    db.add(msg)
    t.updated_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    db.refresh(msg)
    return TicketMessageOut(id=msg.id, sender=msg.sender, body=msg.body, created_at=msg.created_at)
