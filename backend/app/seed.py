"""Seed mock data for the university multi-agent demo.

Runs automatically on app startup when AUTO_SEED is true and the students
table is empty. Can also be invoked directly.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import (
    ChatMessage,
    Course,
    Department,
    Enrollment,
    FinancialRecord,
    Grade,
    GraduationRequirement,
    Hold,
    HousingRecord,
    ITAccount,
    Prerequisite,
    Student,
    Ticket,
    TicketMessage,
    TodoItem,
)
from .security import hash_password


# ---------------------------------------------------------------------------
# GPA helpers (used to derive cumulative GPA / standing from the grade rows)
# ---------------------------------------------------------------------------

_GRADE_POINTS = {
    "A+": 4.0, "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0, "D-": 0.7,
    "F":  0.0, "W": None, "I": None,
}


def grade_points(letter: str) -> float | None:
    return _GRADE_POINTS.get(letter.upper())


def compute_cumulative_gpa(grades: list[tuple[str, int]]) -> tuple[float, int]:
    """grades = [(letter, credits), ...] → (cumulative GPA, credits earned)."""
    total_pts = 0.0
    total_credits = 0
    earned_credits = 0
    for letter, credits in grades:
        gp = grade_points(letter)
        if gp is None:  # W / I — skipped from GPA
            continue
        total_pts += gp * credits
        total_credits += credits
        if gp >= 1.7:  # C- or better = "earned"
            earned_credits += credits
    if total_credits == 0:
        return 0.0, 0
    return round(total_pts / total_credits, 2), earned_credits


def derive_standing(gpa: float) -> str:
    if gpa >= 3.5:
        return "dean's_list"
    if gpa >= 2.0:
        return "good"
    if gpa >= 1.5:
        return "warning"
    return "probation"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------------------
# Seed entrypoints
# ---------------------------------------------------------------------------

def reset_and_seed() -> None:
    """Drop all tables, recreate, and seed."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed(db)
        db.commit()
    finally:
        db.close()


def seed_if_empty() -> None:
    """Create tables if missing; seed only if students table is empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Student).count() > 0:
            return
        _seed(db)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# The actual seed
# ---------------------------------------------------------------------------

def _seed(db: Session) -> None:
    # ---------- Departments ----------
    departments = [
        Department(code="REGISTRAR", name="Office of the Registrar",
                   contact_email="registrar@mock-university.edu",
                   description="Handles enrollment, registration, transcripts, drops, adds, holds related to academic records."),
        Department(code="ADVISING", name="Academic Advising Center",
                   contact_email="advising@mock-university.edu",
                   description="Helps with degree planning, prerequisites, graduation checks, and course selection."),
        Department(code="FINANCIAL", name="Financial Aid & Bursar",
                   contact_email="finaid@mock-university.edu",
                   description="Tuition, scholarships, financial holds, billing questions, payment plans."),
        Department(code="IT", name="IT Help Desk",
                   contact_email="ithelp@mock-university.edu",
                   description="Account access, password resets, SSO, campus Wi-Fi, email quota."),
        Department(code="HOUSING", name="Housing & Dining Services",
                   contact_email="housing@mock-university.edu",
                   description="Residence halls, room assignments, meal plans, dining dollars."),
    ]
    db.add_all(departments)
    db.flush()
    dept_by_code = {d.code: d for d in departments}

    # ---------- Courses ----------
    courses_data = [
        ("CS101", "Intro to Computer Science", 3, "Foundations of programming and computational thinking."),
        ("CS201", "Data Structures", 3, "Lists, trees, hashing, graphs. Requires CS101."),
        ("CS301", "Algorithms", 3, "Design and analysis of algorithms. Requires CS201."),
        ("CS340", "Operating Systems", 3, "Processes, memory, scheduling. Requires CS201."),
        ("CS370", "Databases", 3, "SQL, normalization, transactions. Requires CS201."),
        ("CS450", "Capstone Project", 3, "Senior capstone. Requires CS301."),
        ("MATH151", "Calculus I", 4, "Limits, derivatives, integrals."),
        ("MATH152", "Calculus II", 4, "Series and techniques of integration. Requires MATH151."),
        ("MATH220", "Linear Algebra", 3, "Vectors, matrices, eigenvalues. Requires MATH151."),
        ("ENG101", "Composition I", 3, "Academic writing."),
        ("ENG102", "Composition II", 3, "Research writing. Requires ENG101."),
        ("PHIL120", "Critical Thinking", 3, "Logic and argumentation."),
        ("BIO101", "General Biology", 4, "Cell biology, genetics."),
    ]
    courses: dict[str, Course] = {}
    for code, name, credits, desc in courses_data:
        c = Course(code=code, name=name, credits=credits, description=desc)
        db.add(c)
        courses[code] = c
    db.flush()

    # Prerequisites
    prereqs = [
        ("CS201", "CS101"),
        ("CS301", "CS201"),
        ("CS340", "CS201"),
        ("CS370", "CS201"),
        ("CS450", "CS301"),
        ("MATH152", "MATH151"),
        ("MATH220", "MATH151"),
        ("ENG102", "ENG101"),
    ]
    for course_code, prereq_code in prereqs:
        db.add(Prerequisite(course_id=courses[course_code].id, prereq_course_id=courses[prereq_code].id))

    # Graduation requirements (CS major)
    cs_required = ["CS101", "CS201", "CS301", "CS340", "CS370", "CS450",
                   "MATH151", "MATH152", "MATH220", "ENG101", "ENG102", "PHIL120"]
    for code in cs_required:
        category = "major" if (code.startswith("CS") or code.startswith("MATH")) else "ge"
        db.add(GraduationRequirement(major="Computer Science",
                                     required_course_id=courses[code].id, category=category))

    # ---------- Students ----------
    students_data = [
        dict(email="alice@mock-university.edu", password="password123",
             full_name="Alice Nguyen", student_number="S1001",
             major="Computer Science", year=2),
        dict(email="bob@mock-university.edu", password="password123",
             full_name="Bob Patel", student_number="S1002",
             major="Computer Science", year=3),
        dict(email="carla@mock-university.edu", password="password123",
             full_name="Carla Rodriguez", student_number="S1003",
             major="Computer Science", year=4),
    ]
    students: list[Student] = []
    for sd in students_data:
        s = Student(
            email=sd["email"],
            password_hash=hash_password(sd["password"]),
            full_name=sd["full_name"],
            student_number=sd["student_number"],
            major=sd["major"],
            year=sd["year"],
            gpa=0.0,
            academic_standing="good",
            credits_completed=0,
        )
        db.add(s)
        students.append(s)
    db.flush()
    alice, bob, carla = students

    # ---------- Per-student grade history across 3 terms ----------
    # Each entry: (term, course_code, letter_grade)
    # Spring 2026 = "in progress" (no grade yet) — represented as Enrollments only.

    alice_grades = [
        # Fall 2024 — freshman year fall
        ("Fall 2024", "CS101",  "A"),
        ("Fall 2024", "MATH151","A-"),
        ("Fall 2024", "ENG101", "B+"),
        ("Fall 2024", "PHIL120","A"),
        # Spring 2025 — freshman year spring
        ("Spring 2025", "MATH152", "A-"),
        ("Spring 2025", "ENG102",  "A"),
        ("Spring 2025", "BIO101",  "B+"),
        # Fall 2025 — start of sophomore year (current completed term)
        ("Fall 2025", "CS201",   "A-"),
        ("Fall 2025", "MATH220", "A"),
    ]
    alice_enrolled_now = [("Spring 2026", "CS301"), ("Spring 2026", "CS370")]

    bob_grades = [
        # Fall 2024 — sophomore fall
        ("Fall 2024", "CS101",  "B"),
        ("Fall 2024", "MATH151","C"),
        ("Fall 2024", "ENG101", "B"),
        # Spring 2025
        ("Spring 2025", "MATH152","C+"),
        ("Spring 2025", "PHIL120","B-"),
        # Fall 2025 — junior fall (current completed term)
        ("Fall 2025", "CS201", "D"),   # ← the prereq issue for CS301
        ("Fall 2025", "ENG102","C"),
    ]
    bob_enrolled_now: list[tuple[str, str]] = []  # Bob has no current enrollment (held up)

    carla_grades = [
        # Fall 2023 — sophomore fall
        ("Fall 2023", "CS101",  "A"),
        ("Fall 2023", "MATH151","A"),
        ("Fall 2023", "ENG101", "A-"),
        # Spring 2024
        ("Spring 2024", "CS201",  "A-"),
        ("Spring 2024", "MATH152","A-"),
        ("Spring 2024", "ENG102", "A"),
        ("Spring 2024", "PHIL120","A-"),
        # Fall 2024 — junior fall
        ("Fall 2024", "CS301", "A"),
        ("Fall 2024", "MATH220","A"),
        ("Fall 2024", "BIO101","B+"),
        # Spring 2025 — junior spring
        ("Spring 2025", "CS340","B+"),
        ("Spring 2025", "CS370","A-"),
    ]
    carla_enrolled_now = [("Spring 2026", "CS450")]

    grade_book: dict[Student, list[tuple[str, str]]] = {
        alice: alice_grades,
        bob:   bob_grades,
        carla: carla_grades,
    }
    enroll_now: dict[Student, list[tuple[str, str]]] = {
        alice: alice_enrolled_now,
        bob:   bob_enrolled_now,
        carla: carla_enrolled_now,
    }

    for student, gradelist in grade_book.items():
        gpa_input: list[tuple[str, int]] = []
        for term, code, letter in gradelist:
            db.add(Grade(student_id=student.id, course_id=courses[code].id, term=term, grade=letter))
            gpa_input.append((letter, courses[code].credits))
        cum_gpa, earned = compute_cumulative_gpa(gpa_input)
        student.gpa = cum_gpa
        student.credits_completed = earned
        student.academic_standing = derive_standing(cum_gpa)

    for student, enrolls in enroll_now.items():
        for term, code in enrolls:
            db.add(Enrollment(student_id=student.id, course_id=courses[code].id,
                              term=term, status="enrolled"))

    # ---------- Holds / Financial / IT / Housing / To-dos ----------
    # Alice: clean account, on dean's list (computed)
    db.add(FinancialRecord(student_id=alice.id, balance_due=0.0, tuition_charged=12000.0,
                           scholarships=2000.0, last_payment=10000.0,
                           payment_due_date=_utcnow() + dt.timedelta(days=90)))
    db.add(ITAccount(student_id=alice.id, sso_status="active", email_used_mb=4200, wifi_enabled=True))
    db.add(HousingRecord(student_id=alice.id, has_housing=True, building="North Hall", room="214",
                         meal_plan="Unlimited", dining_balance=325.50))
    db.add(TodoItem(student_id=alice.id, title="Submit FAFSA renewal",
                    detail="Due before next academic year.",
                    due_date=_utcnow() + dt.timedelta(days=60)))

    # Bob: in trouble — financial + advising holds, locked SSO, D in CS201 prereq
    db.add(FinancialRecord(student_id=bob.id, balance_due=1250.75, tuition_charged=12000.0,
                           scholarships=500.0, last_payment=10249.25,
                           payment_due_date=_utcnow() - dt.timedelta(days=10)))
    db.add(Hold(student_id=bob.id, department_id=dept_by_code["FINANCIAL"].id,
                hold_type="financial",
                reason="Unpaid balance of $1,250.75 from Fall 2025. Pay or set up a plan with the Bursar to clear this hold."))
    db.add(Hold(student_id=bob.id, department_id=dept_by_code["ADVISING"].id,
                hold_type="advising",
                reason="Mandatory advising meeting required before Spring 2026 registration."))
    db.add(ITAccount(student_id=bob.id, sso_status="locked", email_used_mb=14800,
                     last_login_failure="Too many failed login attempts on 2026-05-19. Account auto-locked.",
                     wifi_enabled=True))
    db.add(HousingRecord(student_id=bob.id, has_housing=False))
    db.add(TodoItem(student_id=bob.id, title="Pay outstanding balance",
                    detail="$1,250.75 due to clear financial hold.",
                    due_date=_utcnow() - dt.timedelta(days=10)))
    db.add(TodoItem(student_id=bob.id, title="Schedule advising meeting",
                    detail="Required before registering for Spring 2026.",
                    due_date=_utcnow() + dt.timedelta(days=14)))

    # Carla: senior on dean's list, taking the capstone
    db.add(FinancialRecord(student_id=carla.id, balance_due=0.0, tuition_charged=12000.0,
                           scholarships=8000.0, last_payment=4000.0,
                           payment_due_date=_utcnow() + dt.timedelta(days=120)))
    db.add(ITAccount(student_id=carla.id, sso_status="active", email_used_mb=9500, wifi_enabled=True))
    db.add(HousingRecord(student_id=carla.id, has_housing=True, building="South Tower", room="512",
                         meal_plan="Block 160", dining_balance=87.20))
    db.add(TodoItem(student_id=carla.id, title="Apply for graduation",
                    detail="Submit graduation application via the Registrar portal.",
                    due_date=_utcnow() + dt.timedelta(days=30)))

    db.flush()
