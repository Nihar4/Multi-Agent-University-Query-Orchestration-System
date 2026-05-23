"""Thin wrapper around the LangGraph agent system.

Kept as a separate module so the rest of the app (api/chat.py) imports a
stable surface even if the graph implementation evolves.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Student
from .graph import OrchestratorOutput, handle_question as _graph_handle


def handle_question(db: Session, student: Student, question: str) -> OrchestratorOutput:
    return _graph_handle(db, student, question)
