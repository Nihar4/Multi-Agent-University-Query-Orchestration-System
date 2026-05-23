"""Signup / login / me endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FinancialRecord, HousingRecord, ITAccount, Student
from ..schemas import LoginRequest, SignupRequest, StudentOut, TokenResponse
from ..security import create_access_token, get_current_student, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _next_student_number(db: Session) -> str:
    count = db.query(Student).count()
    return f"S{2000 + count + 1}"


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(Student).filter(Student.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    student_number = payload.student_number or _next_student_number(db)
    if db.query(Student).filter(Student.student_number == student_number).first():
        student_number = _next_student_number(db)

    student = Student(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        student_number=student_number,
        major=payload.major or "Computer Science",
        year=payload.year or 1,
        gpa=0.0,
    )
    db.add(student)
    db.flush()

    # Create empty per-student state so agent tools have rows to read.
    db.add(FinancialRecord(student_id=student.id))
    db.add(ITAccount(student_id=student.id))
    db.add(HousingRecord(student_id=student.id))
    db.commit()
    db.refresh(student)

    token = create_access_token(sub=str(student.id))
    return TokenResponse(
        access_token=token,
        student_id=student.id,
        full_name=student.full_name,
        email=student.email,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.email == payload.email).first()
    if not student or not verify_password(payload.password, student.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(sub=str(student.id))
    return TokenResponse(
        access_token=token,
        student_id=student.id,
        full_name=student.full_name,
        email=student.email,
    )


@router.post("/login-form", response_model=TokenResponse, include_in_schema=False)
def login_form(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password grant form variant — used by FastAPI's Swagger 'Authorize' button."""
    student = db.query(Student).filter(Student.email == form.username).first()
    if not student or not verify_password(form.password, student.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(sub=str(student.id))
    return TokenResponse(
        access_token=token,
        student_id=student.id,
        full_name=student.full_name,
        email=student.email,
    )


@router.get("/me", response_model=StudentOut)
def me(current: Student = Depends(get_current_student)):
    return current
