"""LangChain tool builders.

Each department's tools are built per-request because they need to close
over the current (db session, student_id). The underlying read functions
live in `app.agents.tools` — we just wrap them as LangChain StructuredTools.
"""
from __future__ import annotations

from typing import Any, Callable

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import tools as raw  # raw db-read functions


class _NoArgs(BaseModel):
    """No arguments."""


class _CourseCodeArgs(BaseModel):
    course_code: str = Field(description="Course code such as CS301.")


def _wrap_noargs(name: str, description: str, fn: Callable[[Session, int], dict[str, Any]],
                 db: Session, student_id: int) -> BaseTool:
    def _runner() -> dict[str, Any]:
        return fn(db, student_id)
    return StructuredTool.from_function(
        func=_runner,
        name=name,
        description=description,
        args_schema=_NoArgs,
    )


def _wrap_course_code(name: str, description: str,
                      fn: Callable[[Session, int, str], dict[str, Any]],
                      db: Session, student_id: int) -> BaseTool:
    def _runner(course_code: str) -> dict[str, Any]:
        return fn(db, student_id, course_code)
    return StructuredTool.from_function(
        func=_runner,
        name=name,
        description=description,
        args_schema=_CourseCodeArgs,
    )


def build_registrar_tools(db: Session, student_id: int) -> list[BaseTool]:
    return [
        _wrap_noargs(
            "reg_get_holds",
            "List all active holds on the student's account from any department.",
            raw.reg_get_holds, db, student_id,
        ),
        _wrap_noargs(
            "reg_get_current_enrollment",
            "List courses the student is currently enrolled in.",
            raw.reg_get_current_enrollment, db, student_id,
        ),
        _wrap_course_code(
            "reg_check_enrollment_eligibility",
            "Check whether the student can enroll in a specific course. Returns blocking holds, prerequisite status, and final eligibility. Argument: course_code (e.g. 'CS301').",
            raw.reg_check_enrollment_eligibility, db, student_id,
        ),
        _wrap_noargs(
            "reg_get_transcript",
            "Return the student's full transcript with course, term, grade.",
            raw.reg_get_transcript, db, student_id,
        ),
        _wrap_course_code(
            "reg_get_grade_for_course",
            "Return the student's grade for a specific course. Argument: course_code.",
            raw.reg_get_grade_for_course, db, student_id,
        ),
    ]


def build_advising_tools(db: Session, student_id: int) -> list[BaseTool]:
    return [
        _wrap_noargs(
            "adv_graduation_progress",
            "Return graduation progress for the student's major: completed, in-progress, and remaining required courses.",
            raw.adv_graduation_progress, db, student_id,
        ),
        _wrap_course_code(
            "adv_get_prerequisites",
            "Return the prerequisites for a given course. Argument: course_code.",
            raw.adv_get_prerequisites, db, student_id,
        ),
        _wrap_noargs(
            "adv_get_todos",
            "List the student's incomplete to-do items / action items.",
            raw.adv_get_todos, db, student_id,
        ),
        _wrap_noargs(
            "adv_get_transcript",
            "Return the student's full transcript.",
            raw.reg_get_transcript, db, student_id,
        ),
        _wrap_noargs(
            "adv_get_term_gpa",
            "Return per-term GPA breakdown plus cumulative GPA and total credits earned.",
            raw.adv_get_term_gpa, db, student_id,
        ),
        _wrap_noargs(
            "adv_get_academic_standing",
            "Return the student's academic standing (dean's_list / good / warning / probation) with cumulative GPA and explanation.",
            raw.adv_get_academic_standing, db, student_id,
        ),
        _wrap_course_code(
            "adv_get_grade_for_course",
            "Return the student's grade for a specific course. Argument: course_code.",
            raw.reg_get_grade_for_course, db, student_id,
        ),
    ]


def build_financial_tools(db: Session, student_id: int) -> list[BaseTool]:
    return [
        _wrap_noargs(
            "fin_get_account",
            "Return the student's financial summary: balance due, tuition, scholarships, payment date, overdue flag.",
            raw.fin_get_account, db, student_id,
        ),
        _wrap_noargs(
            "fin_get_financial_holds",
            "List active FINANCIAL holds on the student's account.",
            raw.fin_get_financial_holds, db, student_id,
        ),
    ]


def build_it_tools(db: Session, student_id: int) -> list[BaseTool]:
    return [
        _wrap_noargs(
            "it_get_account_status",
            "Return the student's IT account state: SSO status (active/locked), email quota usage, Wi-Fi enabled, last login failure reason.",
            raw.it_get_account_status, db, student_id,
        ),
    ]


def build_housing_tools(db: Session, student_id: int) -> list[BaseTool]:
    return [
        _wrap_noargs(
            "housing_get_record",
            "Return the student's housing assignment and meal plan record.",
            raw.housing_get_record, db, student_id,
        ),
    ]


DEPT_TOOL_BUILDERS: dict[str, Callable[[Session, int], list[BaseTool]]] = {
    "REGISTRAR": build_registrar_tools,
    "ADVISING": build_advising_tools,
    "FINANCIAL": build_financial_tools,
    "IT": build_it_tools,
    "HOUSING": build_housing_tools,
}
