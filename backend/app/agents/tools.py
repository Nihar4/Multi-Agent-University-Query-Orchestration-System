"""Tool definitions for each department agent.

Each tool is a small Python function that takes (db, student_id, **kwargs) and
returns a JSON-serializable dict. We also expose an OpenAI-style JSONSchema
description for each tool so the LLM can call it.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..models import (
    Course,
    Enrollment,
    FinancialRecord,
    Grade,
    GraduationRequirement,
    Hold,
    HousingRecord,
    ITAccount,
    Prerequisite,
    Student,
    TodoItem,
)


# ============================================================================
# REGISTRAR tools — enrollment, holds, registration
# ============================================================================

def reg_get_holds(db: Session, student_id: int) -> dict[str, Any]:
    rows = (
        db.query(Hold)
        .filter(Hold.student_id == student_id, Hold.active.is_(True))
        .all()
    )
    return {
        "active_holds": [
            {
                "hold_type": h.hold_type,
                "reason": h.reason,
                "department": h.department.name if h.department else "",
                "department_code": h.department.code if h.department else "",
            }
            for h in rows
        ],
        "count": len(rows),
    }


def reg_get_current_enrollment(db: Session, student_id: int) -> dict[str, Any]:
    rows = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == student_id, Enrollment.status == "enrolled")
        .all()
    )
    return {
        "enrolled_courses": [
            {"code": e.course.code, "name": e.course.name, "term": e.term, "status": e.status}
            for e in rows
        ]
    }


def reg_check_enrollment_eligibility(db: Session, student_id: int, course_code: str) -> dict[str, Any]:
    """Check if a student can enroll in a course. Returns a structured eligibility report."""
    course = db.query(Course).filter(Course.code == course_code.upper()).first()
    if not course:
        return {"eligible": False, "course_code": course_code, "reason": "Course not found in catalog."}

    # 1) Active holds block enrollment
    holds = (
        db.query(Hold)
        .filter(Hold.student_id == student_id, Hold.active.is_(True))
        .all()
    )
    blocking_holds = [
        {"hold_type": h.hold_type, "reason": h.reason, "department": h.department.name if h.department else ""}
        for h in holds
    ]

    # 2) Prerequisite check — need a passing grade (anything other than F/D/W)
    prereqs = db.query(Prerequisite).filter(Prerequisite.course_id == course.id).all()
    prereq_status = []
    missing_prereqs = []
    for p in prereqs:
        prereq_course = p.prereq
        grade_row = (
            db.query(Grade)
            .filter(Grade.student_id == student_id, Grade.course_id == prereq_course.id)
            .order_by(Grade.id.desc())
            .first()
        )
        if grade_row is None:
            prereq_status.append({"course": prereq_course.code, "grade": None, "passed": False})
            missing_prereqs.append(prereq_course.code)
        else:
            passed = grade_row.grade.upper() not in ("F", "D", "D+", "D-", "W")
            prereq_status.append({"course": prereq_course.code, "grade": grade_row.grade, "passed": passed})
            if not passed:
                missing_prereqs.append(f"{prereq_course.code} (got {grade_row.grade}, need C or better)")

    # 3) Already enrolled?
    already = (
        db.query(Enrollment)
        .filter(
            Enrollment.student_id == student_id,
            Enrollment.course_id == course.id,
            Enrollment.status == "enrolled",
        )
        .first()
    )

    eligible = not blocking_holds and not missing_prereqs and already is None

    return {
        "eligible": eligible,
        "course_code": course.code,
        "course_name": course.name,
        "blocking_holds": blocking_holds,
        "prerequisite_status": prereq_status,
        "missing_or_failed_prereqs": missing_prereqs,
        "already_enrolled": already is not None,
    }


def reg_get_transcript(db: Session, student_id: int) -> dict[str, Any]:
    rows = db.query(Grade).filter(Grade.student_id == student_id).all()
    return {
        "transcript": [
            {"course_code": g.course.code, "course_name": g.course.name, "term": g.term, "grade": g.grade}
            for g in rows
        ]
    }


def reg_get_grade_for_course(db: Session, student_id: int, course_code: str) -> dict[str, Any]:
    course = db.query(Course).filter(Course.code == course_code.upper()).first()
    if not course:
        return {"error": f"Course {course_code} not found in catalog."}
    row = (
        db.query(Grade)
        .filter(Grade.student_id == student_id, Grade.course_id == course.id)
        .order_by(Grade.id.desc())
        .first()
    )
    if not row:
        return {"course_code": course.code, "course_name": course.name, "taken": False}
    return {"course_code": course.code, "course_name": course.name, "taken": True,
            "term": row.term, "grade": row.grade}


# ============================================================================
# ADVISING tools — degree progress, graduation, prerequisites
# ============================================================================

def adv_graduation_progress(db: Session, student_id: int) -> dict[str, Any]:
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        return {"error": "Student not found."}

    reqs = db.query(GraduationRequirement).filter(GraduationRequirement.major == student.major).all()
    completed_course_ids = {
        g.course_id
        for g in db.query(Grade).filter(Grade.student_id == student_id).all()
        if g.grade.upper() not in ("F", "D", "D-", "W")
    }
    enrolled_course_ids = {
        e.course_id
        for e in db.query(Enrollment)
        .filter(Enrollment.student_id == student_id, Enrollment.status == "enrolled")
        .all()
    }

    completed: list[dict[str, str]] = []
    in_progress: list[dict[str, str]] = []
    remaining: list[dict[str, str]] = []
    for r in reqs:
        item = {"code": r.course.code, "name": r.course.name, "category": r.category}
        if r.required_course_id in completed_course_ids:
            completed.append(item)
        elif r.required_course_id in enrolled_course_ids:
            in_progress.append(item)
        else:
            remaining.append(item)

    return {
        "major": student.major,
        "completed_courses": completed,
        "in_progress_courses": in_progress,
        "remaining_courses": remaining,
        "total_required": len(reqs),
        "completed_count": len(completed),
        "in_progress_count": len(in_progress),
        "remaining_count": len(remaining),
    }


def adv_get_prerequisites(db: Session, student_id: int, course_code: str) -> dict[str, Any]:
    course = db.query(Course).filter(Course.code == course_code.upper()).first()
    if not course:
        return {"error": f"Course {course_code} not found."}
    rows = db.query(Prerequisite).filter(Prerequisite.course_id == course.id).all()
    return {
        "course": course.code,
        "course_name": course.name,
        "prerequisites": [{"code": r.prereq.code, "name": r.prereq.name} for r in rows],
    }


def adv_get_todos(db: Session, student_id: int) -> dict[str, Any]:
    rows = db.query(TodoItem).filter(TodoItem.student_id == student_id, TodoItem.completed.is_(False)).all()
    return {
        "todos": [
            {
                "title": t.title,
                "detail": t.detail,
                "due_date": t.due_date.isoformat() if t.due_date else None,
            }
            for t in rows
        ]
    }


_GRADE_POINTS = {
    "A+": 4.0, "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0, "D-": 0.7,
    "F":  0.0,
}


def _gpa_of(rows: list) -> tuple[float, int]:
    pts = 0.0
    credits = 0
    for g in rows:
        gp = _GRADE_POINTS.get(g.grade.upper())
        if gp is None:
            continue
        pts += gp * g.course.credits
        credits += g.course.credits
    if credits == 0:
        return 0.0, 0
    return round(pts / credits, 2), credits


def adv_get_term_gpa(db: Session, student_id: int) -> dict[str, Any]:
    rows = db.query(Grade).filter(Grade.student_id == student_id).all()
    by_term: dict[str, list] = {}
    for r in rows:
        by_term.setdefault(r.term, []).append(r)
    terms = []
    for term, grade_rows in by_term.items():
        gpa, credits = _gpa_of(grade_rows)
        terms.append({"term": term, "gpa": gpa, "credits": credits,
                      "courses": [{"code": g.course.code, "grade": g.grade} for g in grade_rows]})
    # Sort by chronological term ordering (rough — alphanumeric works for "Fall 2024" etc.
    # Map season order so Spring 2025 < Fall 2025.
    season_order = {"Spring": 0, "Summer": 1, "Fall": 2, "Winter": 3}
    def _key(t):
        parts = t["term"].split()
        if len(parts) == 2 and parts[1].isdigit():
            return (int(parts[1]), season_order.get(parts[0], 0))
        return (0, 0)
    terms.sort(key=_key)
    cum_gpa, cum_credits = _gpa_of(rows)
    return {"terms": terms, "cumulative_gpa": cum_gpa, "credits_earned": cum_credits}


def adv_get_academic_standing(db: Session, student_id: int) -> dict[str, Any]:
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        return {"error": "Student not found."}
    # Re-derive from current grade rows to stay accurate even if grades change.
    rows = db.query(Grade).filter(Grade.student_id == student_id).all()
    gpa, credits = _gpa_of(rows)
    if gpa >= 3.5:
        standing = "dean's_list"
        explanation = "Cumulative GPA is 3.5 or above. Eligible for dean's list recognition."
    elif gpa >= 2.0:
        standing = "good"
        explanation = "Cumulative GPA is 2.0 or above. In good academic standing."
    elif gpa >= 1.5:
        standing = "warning"
        explanation = "Cumulative GPA below 2.0. Academic warning — meet with an advisor."
    else:
        standing = "probation"
        explanation = "Cumulative GPA below 1.5. Academic probation — risk of dismissal."
    return {
        "cumulative_gpa": gpa,
        "credits_earned": credits,
        "academic_standing": standing,
        "explanation": explanation,
    }


# ============================================================================
# FINANCIAL tools — tuition, scholarships, holds
# ============================================================================

def fin_get_account(db: Session, student_id: int) -> dict[str, Any]:
    row = db.query(FinancialRecord).filter(FinancialRecord.student_id == student_id).first()
    if not row:
        return {"error": "No financial record found."}
    return {
        "balance_due": row.balance_due,
        "tuition_charged": row.tuition_charged,
        "scholarships": row.scholarships,
        "last_payment": row.last_payment,
        "payment_due_date": row.payment_due_date.isoformat() if row.payment_due_date else None,
        "is_overdue": (
            row.balance_due > 0
            and row.payment_due_date is not None
            and row.payment_due_date.replace(tzinfo=None) < dt.datetime.utcnow()
        ),
    }


def fin_get_financial_holds(db: Session, student_id: int) -> dict[str, Any]:
    rows = (
        db.query(Hold)
        .filter(Hold.student_id == student_id, Hold.active.is_(True), Hold.hold_type == "financial")
        .all()
    )
    return {
        "financial_holds": [{"reason": h.reason} for h in rows],
        "count": len(rows),
    }


# ============================================================================
# IT tools — accounts, wifi, email quota
# ============================================================================

def it_get_account_status(db: Session, student_id: int) -> dict[str, Any]:
    row = db.query(ITAccount).filter(ITAccount.student_id == student_id).first()
    if not row:
        return {"error": "No IT account record found."}
    quota_pct = (row.email_used_mb / row.email_quota_mb * 100) if row.email_quota_mb else 0
    return {
        "sso_status": row.sso_status,
        "wifi_enabled": row.wifi_enabled,
        "email_used_mb": row.email_used_mb,
        "email_quota_mb": row.email_quota_mb,
        "email_quota_pct": round(quota_pct, 1),
        "last_login_failure": row.last_login_failure,
    }


# ============================================================================
# HOUSING tools — residence + meal plan
# ============================================================================

def housing_get_record(db: Session, student_id: int) -> dict[str, Any]:
    row = db.query(HousingRecord).filter(HousingRecord.student_id == student_id).first()
    if not row:
        return {"error": "No housing record."}
    return {
        "has_housing": row.has_housing,
        "building": row.building,
        "room": row.room,
        "meal_plan": row.meal_plan,
        "dining_balance": row.dining_balance,
    }


# ============================================================================
# Tool schemas + dispatch table
# ============================================================================

# Each entry: (python callable, JSONSchema for the LLM)
ToolEntry = tuple[Callable[..., dict[str, Any]], dict[str, Any]]


def _schema(name: str, description: str, properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


REGISTRAR_TOOLS: dict[str, ToolEntry] = {
    "reg_get_holds": (
        reg_get_holds,
        _schema("reg_get_holds", "List all active holds on the student's account from any department."),
    ),
    "reg_get_current_enrollment": (
        reg_get_current_enrollment,
        _schema("reg_get_current_enrollment", "List courses the student is currently enrolled in."),
    ),
    "reg_check_enrollment_eligibility": (
        reg_check_enrollment_eligibility,
        _schema(
            "reg_check_enrollment_eligibility",
            "Check whether the student can enroll in a specific course. Returns blocking holds, prerequisite status, and final eligibility.",
            properties={"course_code": {"type": "string", "description": "Course code like CS301."}},
            required=["course_code"],
        ),
    ),
    "reg_get_transcript": (
        reg_get_transcript,
        _schema("reg_get_transcript", "Return the student's full transcript (course, term, grade)."),
    ),
}

ADVISING_TOOLS: dict[str, ToolEntry] = {
    "adv_graduation_progress": (
        adv_graduation_progress,
        _schema(
            "adv_graduation_progress",
            "Return graduation progress for the student's major: completed, in-progress, and remaining required courses.",
        ),
    ),
    "adv_get_prerequisites": (
        adv_get_prerequisites,
        _schema(
            "adv_get_prerequisites",
            "Return the prerequisites for a given course.",
            properties={"course_code": {"type": "string"}},
            required=["course_code"],
        ),
    ),
    "adv_get_todos": (
        adv_get_todos,
        _schema("adv_get_todos", "List the student's incomplete to-do items / action items."),
    ),
    "reg_get_transcript": (
        reg_get_transcript,
        _schema("reg_get_transcript", "Return the student's full transcript."),
    ),
}

FINANCIAL_TOOLS: dict[str, ToolEntry] = {
    "fin_get_account": (
        fin_get_account,
        _schema("fin_get_account", "Return the student's financial summary: balance due, tuition, scholarships, payment date, overdue flag."),
    ),
    "fin_get_financial_holds": (
        fin_get_financial_holds,
        _schema("fin_get_financial_holds", "List active FINANCIAL holds on the student's account."),
    ),
}

IT_TOOLS: dict[str, ToolEntry] = {
    "it_get_account_status": (
        it_get_account_status,
        _schema(
            "it_get_account_status",
            "Return the student's IT account state: SSO status (active/locked), email quota usage, Wi-Fi enabled, last login failure reason.",
        ),
    ),
}

HOUSING_TOOLS: dict[str, ToolEntry] = {
    "housing_get_record": (
        housing_get_record,
        _schema("housing_get_record", "Return the student's housing and meal plan record."),
    ),
}


def dispatch(tool_name: str, dept_tools: dict[str, ToolEntry], db: Session, student_id: int, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool call by name with the given args. Returns a JSON-serializable dict."""
    entry = dept_tools.get(tool_name)
    if entry is None:
        return {"error": f"Unknown tool: {tool_name}"}
    fn, _schema_obj = entry
    try:
        return fn(db, student_id, **args)
    except TypeError as exc:
        return {"error": f"Invalid args for {tool_name}: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Tool {tool_name} failed: {exc}"}


def tool_schemas(dept_tools: dict[str, ToolEntry]) -> list[dict[str, Any]]:
    return [entry[1] for entry in dept_tools.values()]
