"""SQLAlchemy ORM models for the university multi-agent system."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    contact_email: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(120))
    student_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    major: Mapped[str] = mapped_column(String(80))
    year: Mapped[int] = mapped_column(Integer, default=1)  # 1=freshman..4=senior
    gpa: Mapped[float] = mapped_column(Float, default=0.0)  # cumulative GPA
    academic_standing: Mapped[str] = mapped_column(String(20), default="good")  # good | warning | probation | dean's_list
    credits_completed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    credits: Mapped[int] = mapped_column(Integer, default=3)
    description: Mapped[str] = mapped_column(Text, default="")


class Prerequisite(Base):
    __tablename__ = "prerequisites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    prereq_course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))

    course = relationship("Course", foreign_keys=[course_id])
    prereq = relationship("Course", foreign_keys=[prereq_course_id])


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    term: Mapped[str] = mapped_column(String(20))  # e.g., "Fall 2026"
    status: Mapped[str] = mapped_column(String(20), default="enrolled")  # enrolled | completed | dropped | waitlisted

    student = relationship("Student")
    course = relationship("Course")


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    term: Mapped[str] = mapped_column(String(20))
    grade: Mapped[str] = mapped_column(String(4))  # "A", "B+", etc.

    student = relationship("Student")
    course = relationship("Course")


class Hold(Base):
    __tablename__ = "holds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    hold_type: Mapped[str] = mapped_column(String(40))  # financial, advising, library, immunization, ...
    reason: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    department = relationship("Department")


class TodoItem(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class FinancialRecord(Base):
    __tablename__ = "financial_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), unique=True)
    balance_due: Mapped[float] = mapped_column(Float, default=0.0)
    tuition_charged: Mapped[float] = mapped_column(Float, default=0.0)
    scholarships: Mapped[float] = mapped_column(Float, default=0.0)
    last_payment: Mapped[float] = mapped_column(Float, default=0.0)
    payment_due_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GraduationRequirement(Base):
    __tablename__ = "graduation_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    major: Mapped[str] = mapped_column(String(80), index=True)
    required_course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    category: Mapped[str] = mapped_column(String(40), default="major")  # major | ge | elective

    course = relationship("Course")


class ITAccount(Base):
    __tablename__ = "it_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), unique=True)
    sso_status: Mapped[str] = mapped_column(String(20), default="active")  # active | locked | suspended
    email_quota_mb: Mapped[int] = mapped_column(Integer, default=15000)
    email_used_mb: Mapped[int] = mapped_column(Integer, default=0)
    last_login_failure: Mapped[str] = mapped_column(String(200), default="")
    wifi_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class HousingRecord(Base):
    __tablename__ = "housing_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), unique=True)
    has_housing: Mapped[bool] = mapped_column(Boolean, default=False)
    building: Mapped[str] = mapped_column(String(80), default="")
    room: Mapped[str] = mapped_column(String(20), default="")
    meal_plan: Mapped[str] = mapped_column(String(40), default="")
    dining_balance: Mapped[float] = mapped_column(Float, default=0.0)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    subject: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)  # AI-generated summary for the dept
    original_question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | in_progress | resolved | closed
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    student = relationship("Student")
    department = relationship("Department")
    messages = relationship("TicketMessage", back_populates="ticket", order_by="TicketMessage.created_at")


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    sender: Mapped[str] = mapped_column(String(20))  # student | agent | department
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    ticket = relationship("Ticket", back_populates="messages")


class ChatMessage(Base):
    """Per-student chat history with the multi-agent system."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    routed_to: Mapped[str] = mapped_column(String(40), default="")  # which dept agent handled it
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
