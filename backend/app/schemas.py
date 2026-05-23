"""Pydantic request/response schemas."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ---------- Auth ----------

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    student_number: str
    major: str = "Computer Science"
    year: int = 1


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    student_id: int
    full_name: str
    email: EmailStr


class StudentOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    student_number: str
    major: str
    year: int
    gpa: float

    class Config:
        from_attributes = True


# ---------- Chat ----------

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    # Departments that handled the query. ["GENERAL"] for smalltalk; 1+ codes otherwise.
    routed_to: list[str]
    # Tickets created in this turn (0 or more).
    ticket_ids: list[int] = []
    trace: list[str] = []


# ---------- Tickets ----------

class TicketMessageOut(BaseModel):
    id: int
    sender: str
    body: str
    created_at: dt.datetime

    class Config:
        from_attributes = True


class TicketOut(BaseModel):
    id: int
    subject: str
    summary: str
    original_question: str
    status: str
    department: str
    department_code: str
    created_at: dt.datetime
    updated_at: dt.datetime
    messages: list[TicketMessageOut] = []


class TicketListItem(BaseModel):
    id: int
    subject: str
    status: str
    department: str
    department_code: str
    created_at: dt.datetime


class TicketReplyRequest(BaseModel):
    body: str


# ---------- Chat history ----------

class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    routed_to: str
    ticket_id: Optional[int] = None
    created_at: dt.datetime

    class Config:
        from_attributes = True
