
import os
import random
from datetime import datetime, date, timedelta
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Boolean, DateTime, text
from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
from models import (
    User,
    Job,
    Application,
    GovernmentJob,
    Notification,
)


# =========================================================
# EXTRA DATABASE TABLES
# =========================================================

class SavedJob(Base):
    __tablename__ = "saved_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    job_id = Column(Integer, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class JobAlert(Base):
    __tablename__ = "job_alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    keyword = Column(String, nullable=True)
    location = Column(String, nullable=True)
    category = Column(String, nullable=True)
    min_match = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=True)
    subject = Column(String, nullable=False)
    category = Column(String, nullable=True)
    message = Column(String, nullable=False)
    status = Column(String, default="Open")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


def migrate_user_type_schema():
    """Repair older CareerConnect databases whose users.user_type constraint
    allowed an old value such as `employee` but not the current `employer`.
    Existing users/data are preserved; only the users table is rebuilt when
    the old SQLite CHECK constraint is detected.
    """
    if engine.url.get_backend_name() != "sqlite":
        Base.metadata.create_all(bind=engine)
        return

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
        ).fetchone()

    if not row or not row[0]:
        Base.metadata.create_all(bind=engine)
        return

    table_sql = str(row[0]).lower()

    # Current schema already supports employer.
    if "employer" in table_sql:
        Base.metadata.create_all(bind=engine)
        return

    # Only rebuild when the old table has a restrictive user_type check.
    if "user_type" not in table_sql or "check" not in table_sql:
        Base.metadata.create_all(bind=engine)
        return

    legacy_name = "users_legacy_careerconnect"

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("DROP TABLE IF EXISTS users_legacy_careerconnect"))
        conn.execute(text("ALTER TABLE users RENAME TO users_legacy_careerconnect"))

    # Create the current users table from the current SQLAlchemy model.
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        old_info = conn.execute(text("PRAGMA table_info(users_legacy_careerconnect)")).fetchall()
        new_info = conn.execute(text("PRAGMA table_info(users)")).fetchall()

    old_columns = {row[1] for row in old_info}
    new_columns = [row[1] for row in new_info]
    common_columns = [column for column in new_columns if column in old_columns]

    if common_columns:
        quoted = ", ".join(f'"{column}"' for column in common_columns)
        with engine.begin() as conn:
            conn.execute(
                text(
                    f'INSERT INTO "users" ({quoted}) '
                    f'SELECT {quoted} FROM "{legacy_name}"'
                )
            )

            # Convert any legacy employer value to the current value.
            conn.execute(
                text(
                    'UPDATE "users" SET "user_type" = \'employer\' '
                    'WHERE lower(COALESCE("user_type", \'\')) = \'employee\''
                )
            )

            conn.execute(text(f'DROP TABLE "{legacy_name}"'))
            conn.execute(text("PRAGMA foreign_keys=ON"))


migrate_user_type_schema()


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="CareerConnect API",
    version="1.0.0",
    description="CareerConnect job search, matching, application and employer platform",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

REAL_JOBS_API = "https://api.jobopportunitiesapi.org/public/jobs"


# =========================================================
# REQUEST MODELS
# =========================================================

class RegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str
    mobile: Optional[str] = None
    user_type: str = "job_seeker"


class LoginRequest(BaseModel):
    identifier: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    password: str


class ProfileRequest(BaseModel):
    email: Optional[str] = None
    full_name: str
    qualification: str
    skills: str
    experience: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    mobile: Optional[str] = None
    state: Optional[str] = None
    job_categories: Optional[str] = None


class JobRequest(BaseModel):
    title: str
    company: str
    category: Optional[str] = None
    job_type: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    qualification: Optional[str] = None
    skills: Optional[str] = None
    experience: Optional[str] = None
    salary: Optional[str] = None
    vacancy_count: int = 1
    deadline: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    employer_id: int


class ApplicationRequest(BaseModel):
    user_id: int
    job_id: int
    cover_letter: Optional[str] = None
    message: Optional[str] = None


class ApplicationStatusRequest(BaseModel):
    status: str


class SavedJobRequest(BaseModel):
    user_id: int
    job_id: int


class JobAlertRequest(BaseModel):
    user_id: int
    keyword: Optional[str] = None
    location: Optional[str] = None
    category: Optional[str] = None
    min_match: int = 0


class SupportRequest(BaseModel):
    user_id: Optional[int] = None
    subject: str
    category: Optional[str] = "General"
    message: str


class SupportChatRequest(BaseModel):
    user_id: Optional[int] = None
    message: str


class NotificationRequest(BaseModel):
    user_id: int
    title: str
    message: str
    notification_type: Optional[str] = "general"


class GovernmentJobRequest(BaseModel):
    title: str
    organization: str
    state: Optional[str] = None
    qualification: Optional[str] = None
    description: Optional[str] = None
    exam_date: Optional[str] = None
    last_date: Optional[str] = None
    notification_url: Optional[str] = None
    source: Optional[str] = None
    is_active: bool = True


# =========================================================
# HELPERS
# =========================================================

def clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def lower_text(value) -> str:
    return clean_text(value).lower()


def split_csv(value):
    if not value:
        return []
    return [
        item.strip()
        for item in str(value).split(",")
        if item.strip()
    ]


def normalize_csv(value):
    return [
        item.lower().strip()
        for item in split_csv(value)
    ]


def parse_date(value):
    if value is None or value == "":
        return None

    if isinstance(value, date):
        return value

    value = clean_text(value)

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None


def is_deadline_expired(value):
    parsed = parse_date(value)
    if not parsed:
        return False
    return parsed < date.today()


def safe_int(value, default=1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def user_to_dict(user: User):
    return {
        "id": user.id,
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "mobile": getattr(user, "mobile", None),
        "password": None,
        "user_type": user.user_type,
        "qualification": getattr(user, "qualification", None),
        "skills": getattr(user, "skills", None),
        "experience": getattr(user, "experience", None),
        "location": getattr(user, "location", None),
        "state": getattr(user, "state", None),
        "salary": getattr(user, "salary", None),
        "job_categories": getattr(user, "job_categories", None),
        "resume_filename": getattr(user, "resume_filename", None),
        "created_at": getattr(user, "created_at", None),
    }


def job_to_dict(job: Job):
    location_parts = [
        clean_text(getattr(job, "city", None)),
        clean_text(getattr(job, "district", None)),
        clean_text(getattr(job, "state", None)),
    ]

    location_parts = [x for x in location_parts if x]

    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "category": getattr(job, "category", None),
        "job_type": getattr(job, "job_type", None),
        "state": getattr(job, "state", None),
        "district": getattr(job, "district", None),
        "city": getattr(job, "city", None),
        "location": ", ".join(location_parts),
        "description": getattr(job, "description", None),
        "qualification": getattr(job, "qualification", None),
        "skills": split_csv(getattr(job, "skills", None)),
        "skills_text": getattr(job, "skills", None),
        "experience": getattr(job, "experience", None),
        "salary": getattr(job, "salary", None),
        "vacancy_count": getattr(job, "vacancy_count", 1),
        "deadline": getattr(job, "deadline", None),
        "source": getattr(job, "source", None),
        "source_url": getattr(job, "source_url", None),
        "employer_id": getattr(job, "employer_id", None),
        "is_active": getattr(job, "is_active", True),
        "created_at": getattr(job, "created_at", None),
    }


def application_to_dict(db: Session, application: Application):
    job = db.query(Job).filter(
        Job.id == application.job_id
    ).first()

    user = db.query(User).filter(
        User.id == application.user_id
    ).first()

    result = {
        "id": application.id,
        "user_id": application.user_id,
        "job_id": application.job_id,
        "status": application.status,
        "cover_letter": getattr(application, "cover_letter", None),
        "message": getattr(application, "message", None),
        "applied_at": getattr(application, "applied_at", None),
        "updated_at": getattr(application, "updated_at", None),
        "job": job_to_dict(job) if job else None,
    }

    if job:
        result["job_title"] = job.title
        result["company"] = job.company
        result["state"] = job.state
        result["district"] = job.district
        result["city"] = job.city

    if user:
        result["candidate"] = user_to_dict(user)
        result["user"] = user_to_dict(user)

    return result


def find_user_by_identifier(db: Session, identifier: str):
    identifier = clean_text(identifier)

    user = (
        db.query(User)
        .filter(User.email == identifier)
        .first()
    )

    if user:
        return user

    if hasattr(User, "mobile"):
        user = (
            db.query(User)
            .filter(User.mobile == identifier)
            .first()
        )

    return user


def qualification_level(value):
    value = lower_text(value)

    if "phd" in value or "ph.d" in value:
        return 7
    if "pg" in value or "post graduate" in value or "postgraduate" in value or "master" in value:
        return 6
    if "ug" in value or "degree" in value or "b.tech" in value or "b.e" in value or "bsc" in value or "b.com" in value:
        return 5
    if "diploma" in value:
        return 4
    if "iti" in value:
        return 3
    if "12th" in value or "hsc" in value or "higher secondary" in value:
        return 2
    if "10th" in value or "sslc" in value or "secondary" in value:
        return 1
    return 0


def calculate_job_match(user: User, job: Job):
    """
    Fixed 100-point matching:
    Skills 40
    Qualification 25
    Location 15
    Experience 10
    Category 10
    """

    score = 0
    matching_skills = []
    missing_skills = []

    user_skills = normalize_csv(getattr(user, "skills", None))
    job_skills = normalize_csv(getattr(job, "skills", None))

    # Skills
    if not job_skills:
        score += 40
    else:
        for job_skill in job_skills:
            found = False

            for user_skill in user_skills:
                if (
                    job_skill in user_skill
                    or user_skill in job_skill
                ):
                    found = True
                    break

            if found:
                score += 40 / len(job_skills)
                matching_skills.append(job_skill)
            else:
                missing_skills.append(job_skill)

    # Qualification
    required_q = lower_text(getattr(job, "qualification", None))
    user_q = lower_text(getattr(user, "qualification", None))

    if not required_q or required_q in ["any", "all", "any qualification"]:
        score += 25
    elif user_q:
        user_level = qualification_level(user_q)
        required_level = qualification_level(required_q)

        if user_q == required_q:
            score += 25
        elif (
            user_level > 0
            and required_level > 0
            and user_level >= required_level
        ):
            score += 25

    # Location
    job_location = " ".join([
        lower_text(getattr(job, "city", None)),
        lower_text(getattr(job, "district", None)),
        lower_text(getattr(job, "state", None)),
    ])

    user_location = lower_text(getattr(user, "location", None))
    user_state = lower_text(getattr(user, "state", None))

    if not job_location:
        score += 15
    elif (
        user_location
        and (
            user_location in job_location
            or job_location in user_location
        )
    ):
        score += 15
    elif user_state and user_state in job_location:
        score += 15

    # Experience
    job_exp = lower_text(getattr(job, "experience", None))
    user_exp = lower_text(getattr(user, "experience", None))

    if not job_exp:
        score += 10
    elif user_exp:
        if (
            user_exp in job_exp
            or job_exp in user_exp
        ):
            score += 10
        elif "fresher" in user_exp and (
            "fresher" in job_exp or "0" in job_exp
        ):
            score += 10

    # Category
    job_category = lower_text(getattr(job, "category", None))
    user_categories = normalize_csv(
        getattr(user, "job_categories", None)
    )

    if not job_category:
        score += 10
    elif user_categories and any(
        job_category in cat or cat in job_category
        for cat in user_categories
    ):
        score += 10

    score = max(0, min(100, round(score)))

    return {
        "match_percentage": score,
        "matching_skills": matching_skills,
        "missing_skills": missing_skills,
    }


def calculate_candidate_match(candidate: User, job: Job):
    return calculate_job_match(candidate, job)


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str = "general",
):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        is_read=False,
    )

    db.add(notification)


def infer_category(title, description):
    text = (
        lower_text(title)
        + " "
        + lower_text(description)
    )

    keywords = [
        ("software", "IT / Software"),
        ("developer", "IT / Software"),
        ("programmer", "IT / Software"),
        ("python", "IT / Software"),
        ("data analyst", "Data / Analytics"),
        ("data scientist", "Data / Analytics"),
        ("accountant", "Finance / Accounting"),
        ("finance", "Finance / Accounting"),
        ("sales", "Sales"),
        ("marketing", "Marketing"),
        ("teacher", "Teaching / Education"),
        ("school", "Teaching / Education"),
        ("nurse", "Healthcare"),
        ("doctor", "Healthcare"),
        ("driver", "Driver"),
        ("electrician", "Electrician"),
        ("plumber", "Plumber"),
        ("painter", "Painter"),
        ("construction", "Construction"),
        ("catering", "Catering"),
        ("hotel", "Hotel / Hospitality"),
        ("hospitality", "Hotel / Hospitality"),
        ("security", "Security"),
        ("housekeeping", "Housekeeping"),
        ("delivery", "Delivery"),
        ("mechanic", "Mechanic"),
        ("factory", "Factory"),
        ("warehouse", "Warehouse"),
        ("office", "Office / Admin"),
        ("admin", "Office / Admin"),
        ("tailor", "Tailor"),
        ("carpenter", "Carpenter"),
        ("agriculture", "Agriculture"),
        ("farm", "Agriculture"),
    ]

    for keyword, category in keywords:
        if keyword in text:
            return category

    return "Other"


def infer_skills(title, description):
    text = (
        lower_text(title)
        + " "
        + lower_text(description)
    )

    skills = [
        "python",
        "java",
        "javascript",
        "react",
        "sql",
        "excel",
        "ms office",
        "communication",
        "customer service",
        "sales",
        "marketing",
        "driving",
        "electrical",
        "welding",
        "plumbing",
        "cooking",
        "catering",
        "security",
        "housekeeping",
        "data entry",
        "accounting",
        "tally",
        "mechanical",
        "machine operation",
        "warehouse",
        "logistics",
        "teaching",
        "carpentry",
    ]

    found = [
        skill
        for skill in skills
        if skill in text
    ]

    return ", ".join(found) if found else clean_text(title)


def sync_live_jobs_from_api(limit=50):
    response = requests.get(
        REAL_JOBS_API,
        params={
            "country": "IN",
            "limit": limit,
            "include_description": "true",
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = (
            data.get("jobs")
            or data.get("results")
            or data.get("data")
            or []
        )
    else:
        records = []

    db = SessionLocal()

    added = 0
    updated = 0
    skipped = 0

    try:
        for item in records:
            if not isinstance(item, dict):
                skipped += 1
                continue

            title = clean_text(
                item.get("title")
                or item.get("job_title")
                or item.get("name")
            )

            if not title:
                skipped += 1
                continue

            company = clean_text(
                item.get("company")
                or item.get("company_name")
                or item.get("organization")
                or item.get("employer")
            ) or "Company not specified"

            description = clean_text(
                item.get("description")
                or item.get("job_description")
                or item.get("details")
            )

            category = clean_text(
                item.get("category")
                or item.get("job_category")
            ) or infer_category(title, description)

            state = clean_text(
                item.get("state")
                or item.get("state_name")
            ) or None

            district = clean_text(
                item.get("district")
                or item.get("district_name")
            ) or None

            city = clean_text(
                item.get("city")
                or item.get("city_name")
                or item.get("location")
            ) or None

            job_type = clean_text(
                item.get("job_type")
                or item.get("employment_type")
                or item.get("type")
            ) or "Not specified"

            qualification = clean_text(
                item.get("qualification")
                or item.get("education")
                or item.get("education_level")
            )

            if not qualification:
                qualification = "Any"

            skills = clean_text(
                item.get("skills")
                or item.get("required_skills")
            )

            if not skills:
                skills = infer_skills(
                    title,
                    description
                )

            experience = clean_text(
                item.get("experience")
                or item.get("experience_required")
            ) or None

            salary = clean_text(
                item.get("salary")
                or item.get("salary_range")
                or item.get("pay")
            ) or None

            vacancy = safe_int(
                item.get("vacancy_count")
                or item.get("vacancies")
                or item.get("positions")
                or 1,
                1,
            )

            deadline = parse_date(
                item.get("deadline")
                or item.get("last_date")
                or item.get("closing_date")
                or item.get("application_deadline")
            )

            source_url = clean_text(
                item.get("apply_url")
                or item.get("application_url")
                or item.get("url")
                or item.get("source_url")
                or item.get("job_url")
            )

            existing = None

            if source_url:
                existing = (
                    db.query(Job)
                    .filter(Job.source_url == source_url)
                    .first()
                )

            if existing is None:
                existing = (
                    db.query(Job)
                    .filter(
                        Job.title == title,
                        Job.company == company,
                        Job.city == city,
                    )
                    .first()
                )

            if existing:
                existing.title = title
                existing.company = company
                existing.category = category
                existing.job_type = job_type
                existing.state = state
                existing.district = district
                existing.city = city
                existing.description = description
                existing.qualification = qualification
                existing.skills = skills
                existing.experience = experience
                existing.salary = salary
                existing.vacancy_count = vacancy
                existing.deadline = deadline
                existing.source = "Live Job Source"
                existing.source_url = source_url or existing.source_url
                existing.is_active = True
                updated += 1
            else:
                new_job = Job(
                    title=title,
                    company=company,
                    category=category,
                    job_type=job_type,
                    state=state,
                    district=district,
                    city=city,
                    description=description,
                    qualification=qualification,
                    skills=skills,
                    experience=experience,
                    salary=salary,
                    vacancy_count=vacancy,
                    deadline=deadline,
                    source="Live Job Source",
                    source_url=source_url or None,
                    employer_id=None,
                    is_active=True,
                )

                db.add(new_job)
                added += 1

        db.commit()

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {
        "new_jobs": added,
        "updated_jobs": updated,
        "skipped": skipped,
        "total_received": len(records),
    }


# =========================================================
# HOME / HEALTH
# =========================================================

@app.get("/")
def home():
    return FileResponse("index.html")


@app.get("/api-info")
def api_info():
    return {
        "name": "CareerConnect",
        "version": "1.0.0",
        "features": [
            "registration",
            "login",
            "profile",
            "resume upload",
            "live jobs",
            "AI job matching",
            "job applications",
            "application tracking",
            "saved jobs",
            "job alerts",
            "notifications",
            "government jobs",
            "employer dashboard",
            "employer applicants",
            "find job seekers",
            "support",
            "resume analysis",
            "career growth",
            "candidate contact",
            "employer job edit and close",
            "automatic job alert processing",
            "location summary",
        ],
    }


# =========================================================
# REGISTRATION
# =========================================================

@app.post("/register")
def register_user(data: RegisterRequest):
    db = SessionLocal()

    try:
        email = clean_text(data.email).lower()

        existing = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Email already registered",
            )

        user_type = clean_text(
            data.user_type
        ).lower()

        if user_type not in [
            "job_seeker",
            "employer",
        ]:
            user_type = "job_seeker"

        user = User(
            full_name=clean_text(data.full_name),
            email=email,
            password=data.password,
            mobile=clean_text(data.mobile) or None,
            user_type=user_type,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "message": "Registration successful!",
            "user": user_to_dict(user),
        }

    finally:
        db.close()


# =========================================================
# LOGIN
# =========================================================

@app.post("/login")
def login_user(data: LoginRequest):
    db = SessionLocal()

    try:
        identifier = clean_text(
            data.identifier
            or data.email
            or data.mobile
        )

        if not identifier:
            raise HTTPException(
                status_code=400,
                detail="Email or mobile is required",
            )

        user = find_user_by_identifier(
            db,
            identifier
        )

        if not user:
            raise HTTPException(
                status_code=401,
                detail="Invalid email/mobile or password",
            )

        if user.password != data.password:
            raise HTTPException(
                status_code=401,
                detail="Invalid email/mobile or password",
            )

        return {
            "message": "Login successful!",
            "user": user_to_dict(user),
        }

    finally:
        db.close()


# =========================================================
# FORGOT PASSWORD
# =========================================================

@app.post("/forgot-password")
def forgot_password(data: dict):
    identifier = clean_text(
        data.get("identifier")
        or data.get("email")
        or data.get("mobile")
    )

    if not identifier:
        raise HTTPException(
            status_code=400,
            detail="Email or mobile is required",
        )

    db = SessionLocal()

    try:
        user = find_user_by_identifier(
            db,
            identifier
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="Account not found",
            )

        otp = str(
            random.randint(100000, 999999)
        )

        user.reset_otp = otp
        user.reset_otp_expires = (
            datetime.utcnow()
            + timedelta(minutes=10)
        )

        db.commit()

        return {
            "message": "OTP generated successfully.",
            "otp": otp,
        }

    finally:
        db.close()


@app.post("/reset-password")
def reset_password(data: dict):
    identifier = clean_text(
        data.get("identifier")
        or data.get("email")
        or data.get("mobile")
    )

    otp = clean_text(
        data.get("otp")
    )

    new_password = clean_text(
        data.get("new_password")
    )

    if not identifier or not otp or not new_password:
        raise HTTPException(
            status_code=400,
            detail="Identifier, OTP and new password are required",
        )

    db = SessionLocal()

    try:
        user = find_user_by_identifier(
            db,
            identifier
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="Account not found",
            )

        if user.reset_otp != otp:
            raise HTTPException(
                status_code=400,
                detail="Invalid OTP",
            )

        expires = user.reset_otp_expires

        if expires and expires < datetime.utcnow():
            raise HTTPException(
                status_code=400,
                detail="OTP has expired",
            )

        user.password = new_password
        user.reset_otp = None
        user.reset_otp_expires = None

        db.commit()

        return {
            "message": "Password reset successful!",
        }

    finally:
        db.close()


# =========================================================
# PROFILE
# =========================================================

@app.get("/profile/{user_id}")
def get_profile(user_id: int):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        return {
            "user": user_to_dict(user)
        }

    finally:
        db.close()


@app.get("/profile")
def get_profile_by_email(email: str):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        return {
            "user": user_to_dict(user)
        }

    finally:
        db.close()


@app.put("/profile/{user_id}")
def update_profile(
    user_id: int,
    data: ProfileRequest,
):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        user.full_name = data.full_name
        user.qualification = data.qualification
        user.skills = data.skills
        user.experience = data.experience
        user.location = data.location
        user.salary = data.salary

        if hasattr(user, "mobile"):
            user.mobile = data.mobile

        if hasattr(user, "state"):
            user.state = data.state

        if hasattr(user, "job_categories"):
            user.job_categories = data.job_categories

        db.commit()
        db.refresh(user)

        return {
            "message": "Profile saved successfully!",
            "user": user_to_dict(user),
        }

    finally:
        db.close()


# Backward-compatible profile update
@app.put("/profile")
def update_profile_by_email(
    data: ProfileRequest,
):
    if not data.email:
        raise HTTPException(
            status_code=400,
            detail="Email is required",
        )

    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.email == data.email)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        user.full_name = data.full_name
        user.qualification = data.qualification
        user.skills = data.skills
        user.experience = data.experience
        user.location = data.location
        user.salary = data.salary

        if hasattr(user, "mobile"):
            user.mobile = data.mobile

        if hasattr(user, "state"):
            user.state = data.state

        if hasattr(user, "job_categories"):
            user.job_categories = data.job_categories

        db.commit()
        db.refresh(user)

        return {
            "message": "Profile saved successfully!",
            "user": user_to_dict(user),
        }

    finally:
        db.close()


@app.post("/profile/{user_id}/resume")
async def upload_resume(
    user_id: int,
    file: UploadFile = File(...),
):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        filename = clean_text(
            file.filename
        )

        extension = (
            filename.split(".")[-1].lower()
            if "." in filename
            else ""
        )

        if extension not in [
            "pdf",
            "doc",
            "docx",
        ]:
            raise HTTPException(
                status_code=400,
                detail="Only PDF, DOC and DOCX files are supported",
            )

        safe_name = (
            f"user_{user_id}_resume.{extension}"
        )

        destination = os.path.join(
            UPLOAD_DIR,
            safe_name
        )

        content = await file.read()

        with open(destination, "wb") as output:
            output.write(content)

        if hasattr(user, "resume_filename"):
            user.resume_filename = safe_name

        db.commit()
        db.refresh(user)

        return {
            "message": "Resume uploaded successfully!",
            "filename": safe_name,
            "user": user_to_dict(user),
        }

    finally:
        db.close()


# =========================================================
# JOBS
# =========================================================

@app.get("/jobs")
def get_jobs(
    search: Optional[str] = None,
    location: Optional[str] = None,
    category: Optional[str] = None,
    job_type: Optional[str] = None,
):
    db = SessionLocal()

    try:
        query = (
            db.query(Job)
            .filter(Job.is_active == True)
        )

        jobs = query.all()

        results = []

        for job in jobs:
            if is_deadline_expired(
                getattr(job, "deadline", None)
            ):
                continue

            text = " ".join([
                lower_text(job.title),
                lower_text(job.company),
                lower_text(job.category),
                lower_text(job.skills),
                lower_text(job.description),
            ])

            job_location = " ".join([
                lower_text(getattr(job, "city", None)),
                lower_text(getattr(job, "district", None)),
                lower_text(getattr(job, "state", None)),
            ])

            if search and lower_text(search) not in text:
                continue

            if (
                location
                and lower_text(location)
                not in job_location
            ):
                continue

            if (
                category
                and lower_text(category)
                not in lower_text(
                    getattr(job, "category", None)
                )
            ):
                continue

            if (
                job_type
                and lower_text(job_type)
                not in lower_text(
                    getattr(job, "job_type", None)
                )
            ):
                continue

            results.append(
                job_to_dict(job)
            )

        return {
            "jobs": results,
            "total": len(results),
        }

    finally:
        db.close()


@app.get("/jobs/matched/{user_id}")
def get_matched_jobs(user_id: int):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        jobs = (
            db.query(Job)
            .filter(Job.is_active == True)
            .all()
        )

        results = []

        for job in jobs:
            if is_deadline_expired(
                getattr(job, "deadline", None)
            ):
                continue

            result = job_to_dict(job)

            match = calculate_job_match(
                user,
                job
            )

            result.update(match)

            results.append(result)

        results.sort(
            key=lambda item:
                item.get("match_percentage", 0),
            reverse=True,
        )

        return {
            "jobs": results,
            "total": len(results),
        }

    finally:
        db.close()


@app.get("/ai-match/{user_id}")
def ai_match(user_id: int):
    return get_matched_jobs(user_id)


@app.get("/jobs/{job_id}")
def get_job(job_id: int):
    db = SessionLocal()

    try:
        job = (
            db.query(Job)
            .filter(Job.id == job_id)
            .first()
        )

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job not found",
            )

        return {
            "job": job_to_dict(job)
        }

    finally:
        db.close()


# =========================================================
# CREATE JOB - EMPLOYER
# =========================================================

@app.post("/jobs")
def create_job(data: JobRequest):
    db = SessionLocal()

    try:
        employer = (
            db.query(User)
            .filter(
                User.id == data.employer_id,
                User.user_type == "employer",
            )
            .first()
        )

        if not employer:
            raise HTTPException(
                status_code=403,
                detail="Valid employer account required",
            )

        job = Job(
            title=data.title,
            company=data.company,
            category=data.category,
            job_type=data.job_type,
            state=data.state,
            district=data.district,
            city=data.city,
            description=data.description,
            qualification=data.qualification,
            skills=data.skills,
            experience=data.experience,
            salary=data.salary,
            vacancy_count=max(
                1,
                data.vacancy_count
            ),
            deadline=parse_date(
                data.deadline
            ),
            source=data.source or "Employer Posted",
            source_url=data.source_url,
            employer_id=data.employer_id,
            is_active=True,
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        # Notify matching seekers.
        seekers = (
            db.query(User)
            .filter(
                User.user_type == "job_seeker"
            )
            .all()
        )

        for seeker in seekers[:500]:
            match = calculate_job_match(
                seeker,
                job
            )

            if match["match_percentage"] >= 60:
                create_notification(
                    db,
                    seeker.id,
                    "New job match",
                    (
                        f"{job.title} at {job.company} "
                        f"matches your profile by "
                        f"{match['match_percentage']}%."
                    ),
                    "job_match",
                )

        # Check saved job alerts immediately when a new employer job is posted.
        alerts = db.query(JobAlert).filter(JobAlert.is_active == True).all()
        for alert in alerts[:1000]:
            if alert.keyword:
                job_text = " ".join([lower_text(job.title), lower_text(job.company), lower_text(job.category), lower_text(job.description), lower_text(job.skills)])
                if lower_text(alert.keyword) not in job_text:
                    continue
            if alert.location:
                job_loc = " ".join([lower_text(job.city), lower_text(job.district), lower_text(job.state)])
                if lower_text(alert.location) not in job_loc:
                    continue
            if alert.category and lower_text(alert.category) not in lower_text(job.category):
                continue
            seeker = db.query(User).filter(User.id == alert.user_id, User.user_type == "job_seeker").first()
            if not seeker:
                continue
            alert_match = calculate_job_match(seeker, job)
            if alert_match["match_percentage"] >= int(alert.min_match or 0):
                create_notification(db, seeker.id, "Job alert", f"{job.title} at {job.company} matches your alert ({alert_match["match_percentage"]}%).", "job_alert")

        db.commit()

        return {
            "message": "Job posted successfully!",
            "job": job_to_dict(job),
        }

    finally:
        db.close()


@app.get("/employer/{employer_id}/jobs")
def get_employer_jobs(employer_id: int):
    db = SessionLocal()

    try:
        employer = (
            db.query(User)
            .filter(
                User.id == employer_id,
                User.user_type == "employer",
            )
            .first()
        )

        if not employer:
            raise HTTPException(
                status_code=404,
                detail="Employer not found",
            )

        jobs = (
            db.query(Job)
            .filter(
                Job.employer_id == employer_id
            )
            .order_by(Job.id.desc())
            .all()
        )

        return {
            "jobs": [
                job_to_dict(job)
                for job in jobs
            ],
            "total": len(jobs),
        }

    finally:
        db.close()


# =========================================================
# APPLICATIONS
# =========================================================

@app.post("/applications")
def create_application(
    data: ApplicationRequest,
):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == data.user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        if user.user_type != "job_seeker":
            raise HTTPException(
                status_code=403,
                detail="Only job seekers can apply",
            )

        job = (
            db.query(Job)
            .filter(Job.id == data.job_id)
            .first()
        )

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job not found",
            )

        if not job.is_active:
            raise HTTPException(
                status_code=400,
                detail="This job is closed",
            )

        if is_deadline_expired(
            getattr(job, "deadline", None)
        ):
            raise HTTPException(
                status_code=400,
                detail="Application deadline has passed",
            )

        existing = (
            db.query(Application)
            .filter(
                Application.user_id == data.user_id,
                Application.job_id == data.job_id,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="You have already applied for this job",
            )

        application = Application(
            user_id=data.user_id,
            job_id=data.job_id,
            status="Applied",
            cover_letter=data.cover_letter,
            message=data.message,
            applied_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(application)
        db.commit()
        db.refresh(application)

        # Employer notification
        if getattr(job, "employer_id", None):
            create_notification(
                db,
                job.employer_id,
                "New job application",
                (
                    f"{user.full_name} applied for "
                    f"{job.title}."
                ),
                "application",
            )

        db.commit()

        return {
            "message": "Application submitted successfully!",
            "application": application_to_dict(
                db,
                application
            ),
        }

    finally:
        db.close()


@app.get("/applications/user/{user_id}")
def get_user_applications(user_id: int):
    db = SessionLocal()

    try:
        applications = (
            db.query(Application)
            .filter(
                Application.user_id == user_id
            )
            .order_by(
                Application.applied_at.desc()
            )
            .all()
        )

        return {
            "applications": [
                application_to_dict(
                    db,
                    app_item
                )
                for app_item in applications
            ],
            "total": len(applications),
        }

    finally:
        db.close()


@app.get("/applications/{application_id}")
def get_application(application_id: int):
    db = SessionLocal()

    try:
        application = (
            db.query(Application)
            .filter(
                Application.id == application_id
            )
            .first()
        )

        if not application:
            raise HTTPException(
                status_code=404,
                detail="Application not found",
            )

        return {
            "application":
                application_to_dict(
                    db,
                    application
                )
        }

    finally:
        db.close()


@app.put("/applications/{application_id}/status")
def update_application_status(
    application_id: int,
    data: ApplicationStatusRequest,
):
    allowed = {
        "Applied",
        "Under Review",
        "Shortlisted",
        "Interview",
        "Selected",
        "Rejected",
        "Withdrawn",
    }

    status = clean_text(data.status)

    if status not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Invalid application status",
        )

    db = SessionLocal()

    try:
        application = (
            db.query(Application)
            .filter(
                Application.id == application_id
            )
            .first()
        )

        if not application:
            raise HTTPException(
                status_code=404,
                detail="Application not found",
            )

        application.status = status
        application.updated_at = datetime.utcnow()

        job = (
            db.query(Job)
            .filter(
                Job.id == application.job_id
            )
            .first()
        )

        if job:
            create_notification(
                db,
                application.user_id,
                f"Application status: {status}",
                (
                    f"Your application for "
                    f"{job.title} at {job.company} "
                    f"is now {status}."
                ),
                "application_status",
            )

        db.commit()

        return {
            "message":
                "Application status updated successfully!",
            "application":
                application_to_dict(
                    db,
                    application
                ),
        }

    finally:
        db.close()


@app.delete("/applications/{application_id}")
def withdraw_application(
    application_id: int,
):
    db = SessionLocal()

    try:
        application = (
            db.query(Application)
            .filter(
                Application.id == application_id
            )
            .first()
        )

        if not application:
            raise HTTPException(
                status_code=404,
                detail="Application not found",
            )

        application.status = "Withdrawn"
        application.updated_at = datetime.utcnow()

        db.commit()

        return {
            "message":
                "Application withdrawn successfully!",
        }

    finally:
        db.close()


# =========================================================
# EMPLOYER APPLICATIONS
# =========================================================

@app.get("/employer/{employer_id}/applications")
def get_employer_applications(
    employer_id: int,
):
    db = SessionLocal()

    try:
        employer = (
            db.query(User)
            .filter(
                User.id == employer_id,
                User.user_type == "employer",
            )
            .first()
        )

        if not employer:
            raise HTTPException(
                status_code=403,
                detail="Valid employer account required",
            )

        jobs = (
            db.query(Job)
            .filter(
                Job.employer_id == employer_id
            )
            .all()
        )

        job_ids = [
            job.id
            for job in jobs
        ]

        if not job_ids:
            return {
                "applications": [],
                "total": 0,
            }

        applications = (
            db.query(Application)
            .filter(
                Application.job_id.in_(job_ids)
            )
            .order_by(
                Application.applied_at.desc()
            )
            .all()
        )

        results = []

        for application in applications:
            job = (
                db.query(Job)
                .filter(
                    Job.id == application.job_id
                )
                .first()
            )

            candidate = (
                db.query(User)
                .filter(
                    User.id == application.user_id
                )
                .first()
            )

            item = application_to_dict(
                db,
                application
            )

            if job and candidate:
                match = calculate_candidate_match(
                    candidate,
                    job
                )

                item.update(match)

                item["candidate"] = (
                    user_to_dict(candidate)
                )

                item["user"] = (
                    user_to_dict(candidate)
                )

            results.append(item)

        return {
            "applications": results,
            "total": len(results),
        }

    finally:
        db.close()


# =========================================================
# NEW FEATURE: EMPLOYER FINDS JOB SEEKERS
# =========================================================

@app.get("/employer/{employer_id}/candidates")
def find_job_seekers(
    employer_id: int,
    search: Optional[str] = None,
    location: Optional[str] = None,
    qualification: Optional[str] = None,
    skill: Optional[str] = None,
    min_match: int = 0,
):
    db = SessionLocal()

    try:
        employer = (
            db.query(User)
            .filter(
                User.id == employer_id,
                User.user_type == "employer",
            )
            .first()
        )

        if not employer:
            raise HTTPException(
                status_code=403,
                detail="Valid employer account required",
            )

        employer_jobs = (
            db.query(Job)
            .filter(
                Job.employer_id == employer_id,
                Job.is_active == True,
            )
            .all()
        )

        seekers = (
            db.query(User)
            .filter(
                User.user_type == "job_seeker"
            )
            .order_by(
                User.created_at.desc()
            )
            .all()
        )

        search_value = lower_text(search)
        location_value = lower_text(location)
        qualification_value = lower_text(qualification)
        skill_value = lower_text(skill)

        results = []

        for candidate in seekers:

            searchable = " ".join([
                lower_text(candidate.full_name),
                lower_text(candidate.email),
                lower_text(getattr(candidate, "mobile", None)),
                lower_text(getattr(candidate, "qualification", None)),
                lower_text(getattr(candidate, "skills", None)),
                lower_text(getattr(candidate, "experience", None)),
                lower_text(getattr(candidate, "location", None)),
                lower_text(getattr(candidate, "state", None)),
                lower_text(getattr(candidate, "job_categories", None)),
            ])

            if (
                search_value
                and search_value not in searchable
            ):
                continue

            candidate_location = " ".join([
                lower_text(
                    getattr(candidate, "location", None)
                ),
                lower_text(
                    getattr(candidate, "state", None)
                ),
            ])

            if (
                location_value
                and location_value not in candidate_location
            ):
                continue

            if (
                qualification_value
                and qualification_value
                not in lower_text(
                    getattr(
                        candidate,
                        "qualification",
                        None
                    )
                )
            ):
                continue

            candidate_skill_text = lower_text(
                getattr(candidate, "skills", None)
            )

            if (
                skill_value
                and skill_value not in candidate_skill_text
            ):
                continue

            best_match = 0
            best_job = None
            best_match_data = {
                "matching_skills": [],
                "missing_skills": [],
            }

            for job in employer_jobs:
                match_data = calculate_candidate_match(
                    candidate,
                    job
                )

                current_score = (
                    match_data["match_percentage"]
                )

                if current_score > best_match:
                    best_match = current_score
                    best_job = job
                    best_match_data = match_data

            if not employer_jobs:
                best_match = 0

            if best_match < max(0, min_match):
                continue

            results.append({
                "id": candidate.id,
                "full_name": candidate.full_name,
                "email": candidate.email,
                "mobile": getattr(candidate, "mobile", None),
                "qualification": getattr(
                    candidate,
                    "qualification",
                    None
                ),
                "skills": getattr(
                    candidate,
                    "skills",
                    None
                ),
                "experience": getattr(
                    candidate,
                    "experience",
                    None
                ),
                "location": getattr(
                    candidate,
                    "location",
                    None
                ),
                "state": getattr(
                    candidate,
                    "state",
                    None
                ),
                "salary": getattr(
                    candidate,
                    "salary",
                    None
                ),
                "job_categories": getattr(
                    candidate,
                    "job_categories",
                    None
                ),
                "resume_filename": getattr(
                    candidate,
                    "resume_filename",
                    None
                ),
                "match_percentage": best_match,
                "matching_skills": best_match_data[
                    "matching_skills"
                ],
                "missing_skills": best_match_data[
                    "missing_skills"
                ],
                "matched_job": (
                    {
                        "id": best_job.id,
                        "title": best_job.title,
                        "company": best_job.company,
                        "category": best_job.category,
                    }
                    if best_job
                    else None
                ),
            })

        results.sort(
            key=lambda item:
                item["match_percentage"],
            reverse=True,
        )

        return {
            "candidates": results,
            "total": len(results),
        }

    finally:
        db.close()


# =========================================================
# SAVED JOBS
# =========================================================

@app.post("/saved-jobs")
def save_job(data: SavedJobRequest):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == data.user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        job = (
            db.query(Job)
            .filter(Job.id == data.job_id)
            .first()
        )

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job not found",
            )

        existing = (
            db.query(SavedJob)
            .filter(
                SavedJob.user_id == data.user_id,
                SavedJob.job_id == data.job_id,
            )
            .first()
        )

        if existing:
            return {
                "message": "Job already saved!",
                "saved": True,
            }

        saved = SavedJob(
            user_id=data.user_id,
            job_id=data.job_id,
        )

        db.add(saved)
        db.commit()

        return {
            "message": "Job saved successfully!",
            "saved": True,
        }

    finally:
        db.close()


@app.get("/saved-jobs/{user_id}")
def get_saved_jobs(user_id: int):
    db = SessionLocal()

    try:
        saved_items = (
            db.query(SavedJob)
            .filter(
                SavedJob.user_id == user_id
            )
            .order_by(
                SavedJob.created_at.desc()
            )
            .all()
        )

        jobs = []

        for saved in saved_items:
            job = (
                db.query(Job)
                .filter(
                    Job.id == saved.job_id
                )
                .first()
            )

            if job:
                item = job_to_dict(job)
                item["saved_id"] = saved.id
                jobs.append(item)

        return {
            "jobs": jobs,
            "total": len(jobs),
        }

    finally:
        db.close()


@app.delete("/saved-jobs/{user_id}/{job_id}")
def remove_saved_job(
    user_id: int,
    job_id: int,
):
    db = SessionLocal()

    try:
        saved = (
            db.query(SavedJob)
            .filter(
                SavedJob.user_id == user_id,
                SavedJob.job_id == job_id,
            )
            .first()
        )

        if not saved:
            raise HTTPException(
                status_code=404,
                detail="Saved job not found",
            )

        db.delete(saved)
        db.commit()

        return {
            "message": "Saved job removed.",
        }

    finally:
        db.close()


# =========================================================
# JOB ALERTS
# =========================================================

@app.post("/job-alerts")
def create_job_alert(
    data: JobAlertRequest,
):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == data.user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        alert = JobAlert(
            user_id=data.user_id,
            keyword=data.keyword,
            location=data.location,
            category=data.category,
            min_match=max(
                0,
                min(100, data.min_match)
            ),
            is_active=True,
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)

        return {
            "message": "Job alert created successfully!",
            "alert": {
                "id": alert.id,
                "keyword": alert.keyword,
                "location": alert.location,
                "category": alert.category,
                "min_match": alert.min_match,
                "is_active": alert.is_active,
            },
        }

    finally:
        db.close()


@app.get("/job-alerts/{user_id}")
def get_job_alerts(user_id: int):
    db = SessionLocal()

    try:
        alerts = (
            db.query(JobAlert)
            .filter(
                JobAlert.user_id == user_id
            )
            .order_by(
                JobAlert.created_at.desc()
            )
            .all()
        )

        return {
            "alerts": [
                {
                    "id": item.id,
                    "keyword": item.keyword,
                    "location": item.location,
                    "category": item.category,
                    "min_match": item.min_match,
                    "is_active": item.is_active,
                    "created_at": item.created_at,
                }
                for item in alerts
            ]
        }

    finally:
        db.close()


@app.delete("/job-alerts/{alert_id}")
def delete_job_alert(alert_id: int):
    db = SessionLocal()

    try:
        alert = (
            db.query(JobAlert)
            .filter(JobAlert.id == alert_id)
            .first()
        )

        if not alert:
            raise HTTPException(
                status_code=404,
                detail="Job alert not found",
            )

        db.delete(alert)
        db.commit()

        return {
            "message": "Job alert deleted.",
        }

    finally:
        db.close()


# =========================================================
# NOTIFICATIONS
# =========================================================

@app.get("/notifications/{user_id}")
def get_notifications(user_id: int):
    db = SessionLocal()

    try:
        items = (
            db.query(Notification)
            .filter(
                Notification.user_id == user_id
            )
            .order_by(
                Notification.created_at.desc()
            )
            .all()
        )

        return {
            "notifications": [
                {
                    "id": item.id,
                    "title": item.title,
                    "message": item.message,
                    "notification_type":
                        item.notification_type,
                    "is_read": item.is_read,
                    "created_at": item.created_at,
                }
                for item in items
            ]
        }

    finally:
        db.close()


@app.post("/notifications")
def create_notification_api(
    data: NotificationRequest,
):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == data.user_id)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        notification = Notification(
            user_id=data.user_id,
            title=data.title,
            message=data.message,
            notification_type=data.notification_type,
            is_read=False,
        )

        db.add(notification)
        db.commit()
        db.refresh(notification)

        return {
            "message":
                "Notification created successfully!",
        }

    finally:
        db.close()


@app.put("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
):
    db = SessionLocal()

    try:
        item = (
            db.query(Notification)
            .filter(
                Notification.id == notification_id
            )
            .first()
        )

        if not item:
            raise HTTPException(
                status_code=404,
                detail="Notification not found",
            )

        item.is_read = True
        db.commit()

        return {
            "message": "Notification marked as read.",
        }

    finally:
        db.close()


# =========================================================
# SUPPORT
# =========================================================

@app.post("/support")
def create_support_ticket(
    data: SupportRequest,
):
    db = SessionLocal()

    try:
        if data.user_id:
            user = (
                db.query(User)
                .filter(
                    User.id == data.user_id
                )
                .first()
            )

            if not user:
                raise HTTPException(
                    status_code=404,
                    detail="User not found",
                )

        ticket = SupportTicket(
            user_id=data.user_id,
            subject=data.subject,
            category=data.category or "General",
            message=data.message,
            status="Open",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(ticket)
        db.commit()
        db.refresh(ticket)

        if data.user_id:
            create_notification(
                db,
                data.user_id,
                "Support request received",
                (
                    f"Your support request "
                    f"#{ticket.id} has been received."
                ),
                "support",
            )
            db.commit()

        return {
            "message":
                "Your support request was submitted successfully!",
            "ticket_id": ticket.id,
        }

    finally:
        db.close()


@app.get("/support/{user_id}")
def get_user_support_tickets(user_id: int):
    db = SessionLocal()

    try:
        tickets = (
            db.query(SupportTicket)
            .filter(
                SupportTicket.user_id == user_id
            )
            .order_by(
                SupportTicket.created_at.desc()
            )
            .all()
        )

        return {
            "tickets": [
                {
                    "id": item.id,
                    "subject": item.subject,
                    "category": item.category,
                    "message": item.message,
                    "status": item.status,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
                for item in tickets
            ]
        }

    finally:
        db.close()


@app.post("/support/chat")
def support_chat(
    data: SupportChatRequest,
):
    message = lower_text(data.message)

    if not message:
        return {
            "reply":
                "Please type your question."
        }

    if (
        "login" in message
        or "password" in message
    ):
        reply = (
            "For login problems, check your email/mobile "
            "and password. Use Forgot Password to reset it."
        )

    elif (
        "apply" in message
        or "application" in message
    ):
        reply = (
            "Open Jobs, choose a suitable vacancy and "
            "use Apply Now. You can track the application "
            "from My Applications."
        )

    elif (
        "resume" in message
        or "profile" in message
    ):
        reply = (
            "Open My Profile, update your details and "
            "upload your latest resume."
        )

    elif (
        "government" in message
        or "exam" in message
    ):
        reply = (
            "Open Government Jobs and verify the latest "
            "details using the official notification."
        )

    elif (
        "employer" in message
        or "candidate" in message
    ):
        reply = (
            "Employers can post jobs, review applicants "
            "and find job seekers using AI matching."
        )

    else:
        reply = (
            "Thanks for contacting CareerConnect Support. "
            "Please use the Report a Problem form for a "
            "detailed support request."
        )

    return {
        "reply": reply
    }


# =========================================================
# GOVERNMENT JOBS
# =========================================================

@app.get("/government-jobs")
def get_government_jobs(
    state: Optional[str] = None,
    qualification: Optional[str] = None,
    search: Optional[str] = None,
):
    db = SessionLocal()

    try:
        query = (
            db.query(GovernmentJob)
            .filter(
                GovernmentJob.is_active == True
            )
        )

        items = query.all()

        results = []

        for job in items:

            if is_deadline_expired(
                getattr(job, "last_date", None)
            ):
                continue

            text = " ".join([
                lower_text(job.title),
                lower_text(job.organization),
                lower_text(job.description),
            ])

            if (
                search
                and lower_text(search)
                not in text
            ):
                continue

            if (
                state
                and lower_text(state)
                not in lower_text(
                    getattr(job, "state", None)
                )
            ):
                continue

            if (
                qualification
                and lower_text(qualification)
                not in lower_text(
                    getattr(
                        job,
                        "qualification",
                        None
                    )
                )
                and "any" not in lower_text(
                    getattr(
                        job,
                        "qualification",
                        None
                    )
                )
            ):
                continue

            results.append({
                "id": job.id,
                "title": job.title,
                "organization": job.organization,
                "state": getattr(job, "state", None),
                "qualification":
                    getattr(
                        job,
                        "qualification",
                        None
                    ),
                "description":
                    getattr(
                        job,
                        "description",
                        None
                    ),
                "exam_date":
                    getattr(
                        job,
                        "exam_date",
                        None
                    ),
                "last_date":
                    getattr(
                        job,
                        "last_date",
                        None
                    ),
                "notification_url":
                    getattr(
                        job,
                        "notification_url",
                        None
                    ),
                "source":
                    getattr(
                        job,
                        "source",
                        None
                    ),
                "is_active":
                    getattr(
                        job,
                        "is_active",
                        True
                    ),
                "created_at":
                    getattr(
                        job,
                        "created_at",
                        None
                    ),
            })

        return {
            "jobs": results,
            "total": len(results),
        }

    finally:
        db.close()


@app.post("/government-jobs")
def create_government_job(
    data: GovernmentJobRequest,
):
    db = SessionLocal()

    try:
        job = GovernmentJob(
            title=data.title,
            organization=data.organization,
            state=data.state,
            qualification=data.qualification,
            description=data.description,
            exam_date=parse_date(
                data.exam_date
            ),
            last_date=parse_date(
                data.last_date
            ),
            notification_url=data.notification_url,
            source=data.source,
            is_active=data.is_active,
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        return {
            "message":
                "Government job notification created!",
            "id": job.id,
        }

    finally:
        db.close()


# =========================================================
# LIVE JOB SYNC
# =========================================================

@app.post("/sync-real-jobs")
def sync_real_jobs(limit: int = 50):
    limit = max(
        1,
        min(50, limit)
    )

    try:
        result = sync_live_jobs_from_api(
            limit=limit
        )

        return {
            "message":
                "Live jobs synchronized successfully!",
            **result,
        }

    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "Could not connect to live job source: "
                + str(error)
            ),
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Live job sync failed: "
                + str(error)
            ),
        )


# =========================================================
# CATEGORIES / LANGUAGES / LOCATIONS
# =========================================================

@app.get("/categories")
def get_categories():
    categories = [
        "IT / Software",
        "Data / Analytics",
        "Sales",
        "Marketing",
        "Finance / Accounting",
        "Teaching / Education",
        "Healthcare",
        "Driver",
        "Electrician",
        "Plumber",
        "Painter",
        "Construction",
        "Catering",
        "Hotel / Hospitality",
        "Security",
        "Housekeeping",
        "Delivery",
        "Mechanic",
        "Factory",
        "Warehouse",
        "Office / Admin",
        "Tailor",
        "Carpenter",
        "Agriculture",
        "Other",
    ]

    return {
        "categories": categories
    }


@app.get("/languages")
def get_languages():
    languages = [
        {"code": "en", "name": "English"},
        {"code": "ta", "name": "தமிழ்"},
        {"code": "hi", "name": "हिन्दी"},
        {"code": "te", "name": "తెలుగు"},
        {"code": "kn", "name": "ಕನ್ನಡ"},
        {"code": "ml", "name": "മലയാളം"},
        {"code": "mr", "name": "मराठी"},
        {"code": "bn", "name": "বাংলা"},
        {"code": "gu", "name": "ગુજરાતી"},
        {"code": "pa", "name": "ਪੰਜਾਬੀ"},
        {"code": "or", "name": "ଓଡ଼ିଆ"},
        {"code": "ur", "name": "اردو"},
        {"code": "as", "name": "অসমীয়া"},
        {"code": "ne", "name": "नेपाली"},
    ]

    return {
        "languages": languages
    }


@app.get("/locations")
def get_locations():
    return {
        "country": "India",
        "states": [
            "Andhra Pradesh",
            "Arunachal Pradesh",
            "Assam",
            "Bihar",
            "Chhattisgarh",
            "Goa",
            "Gujarat",
            "Haryana",
            "Himachal Pradesh",
            "Jharkhand",
            "Karnataka",
            "Kerala",
            "Madhya Pradesh",
            "Maharashtra",
            "Manipur",
            "Meghalaya",
            "Mizoram",
            "Nagaland",
            "Odisha",
            "Punjab",
            "Rajasthan",
            "Sikkim",
            "Tamil Nadu",
            "Telangana",
            "Tripura",
            "Uttar Pradesh",
            "Uttarakhand",
            "West Bengal",
            "Delhi",
            "Jammu and Kashmir",
            "Ladakh",
            "Puducherry",
        ],
    }


# =========================================================
# STATIC HTML PAGES
# =========================================================


# =========================================================
# FINAL ADD-ON FEATURES
# =========================================================

class JobUpdateRequest(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    category: Optional[str] = None
    job_type: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    qualification: Optional[str] = None
    skills: Optional[str] = None
    experience: Optional[str] = None
    salary: Optional[str] = None
    vacancy_count: Optional[int] = None
    deadline: Optional[str] = None
    is_active: Optional[bool] = None


class CandidateContactRequest(BaseModel):
    message: Optional[str] = None


def _profile_skill_list(user):
    return [x.lower() for x in split_csv(getattr(user, 'skills', None)) if x]


def _recommended_skills_for_user(user):
    categories = lower_text(getattr(user, 'job_categories', None))
    skills = set(_profile_skill_list(user))
    bundles = {
        'it / software': ['python','sql','javascript','git','rest api','html','css','react'],
        'data / analytics': ['excel','sql','python','power bi','statistics','data visualization'],
        'sales': ['communication','negotiation','crm','lead generation','customer service'],
        'marketing': ['digital marketing','seo','social media','content writing','analytics'],
        'finance / accounting': ['excel','tally','accounting','gst','financial analysis'],
        'teaching / education': ['teaching','communication','lesson planning','classroom management'],
        'healthcare': ['patient care','communication','documentation','first aid'],
        'driver': ['driving','road safety','navigation','vehicle maintenance'],
        'electrician': ['electrical','wiring','safety','maintenance'],
        'plumber': ['plumbing','pipe fitting','maintenance','safety'],
        'construction': ['masonry','site safety','measurement','equipment handling'],
        'catering': ['cooking','food safety','kitchen hygiene','customer service'],
        'security': ['security','surveillance','emergency response','communication'],
        'delivery': ['driving','navigation','customer service','logistics'],
        'warehouse': ['inventory','warehouse','logistics','barcode scanning'],
    }
    target=[]
    for key, vals in bundles.items():
        if key in categories:
            target += vals
    if not target:
        target = sum(bundles.values(), [])[:12]
    return [x for x in target if x.lower() not in skills][:8]


def _read_resume_text(path):
    ext = path.lower().rsplit('.', 1)[-1] if '.' in path else ''
    try:
        if ext == 'pdf':
            try:
                from pypdf import PdfReader
                reader = PdfReader(path)
                return '\n'.join((page.extract_text() or '') for page in reader.pages)
            except Exception:
                return ''
        if ext == 'docx':
            try:
                from docx import Document
                doc = Document(path)
                return '\n'.join(p.text for p in doc.paragraphs)
            except Exception:
                return ''
        return ''
    except Exception:
        return ''


def _extract_resume_skills(text):
    catalog = [
        'python','java','javascript','react','html','css','sql','excel','power bi','tableau','git',
        'communication','customer service','sales','marketing','seo','tally','accounting','gst',
        'driving','electrical','welding','plumbing','cooking','catering','security','housekeeping',
        'data entry','teaching','carpentry','mechanical','machine operation','logistics','warehouse',
    ]
    low = lower_text(text)
    return [x for x in catalog if x in low]


@app.get('/profile/{user_id}/resume-analysis')
def resume_analysis(user_id: int):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail='User not found')

        filename = getattr(user, 'resume_filename', None)
        text = ''
        if filename:
            path = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(path):
                text = _read_resume_text(path)

        profile_skills = _profile_skill_list(user)
        resume_skills = _extract_resume_skills(text)
        combined = sorted(set(profile_skills + resume_skills))
        recommended = _recommended_skills_for_user(user)

        completeness = 0
        fields = [user.full_name, user.email, user.qualification, user.skills, user.location, user.job_categories, filename]
        completeness = round(sum(bool(x) for x in fields) / len(fields) * 100)

        return {
            'user_id': user_id,
            'resume_filename': filename,
            'resume_text_available': bool(text),
            'skills_found_in_resume': resume_skills,
            'profile_skills': profile_skills,
            'combined_skills': combined,
            'recommended_skills': recommended,
            'profile_completeness': completeness,
            'resume_tips': [
                'Keep your latest qualification and experience updated.',
                'Use measurable achievements where possible.',
                'Keep skills aligned with the jobs you target.',
                'Use a clear one- or two-page format for most job applications.',
            ],
        }
    finally:
        db.close()


@app.get('/profile/{user_id}/career-growth')
def career_growth(user_id: int):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail='User not found')

        next_skills = _recommended_skills_for_user(user)
        return {
            'career_focus': getattr(user, 'job_categories', None) or 'Choose a job category in your profile',
            'current_skills': split_csv(getattr(user, 'skills', None)),
            'skills_to_improve': next_skills,
            'roadmap': [
                {'step': 1, 'title': 'Complete profile', 'action': 'Add qualification, experience, location, category and resume.'},
                {'step': 2, 'title': 'Build skills', 'action': 'Work on the recommended skills shown above.'},
                {'step': 3, 'title': 'Apply strategically', 'action': 'Prioritize jobs with strong AI match and relevant requirements.'},
                {'step': 4, 'title': 'Track progress', 'action': 'Use My Applications and update your profile regularly.'},
            ],
        }
    finally:
        db.close()


@app.get('/resumes/{user_id}')
def download_resume(user_id: int):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not getattr(user, 'resume_filename', None):
            raise HTTPException(status_code=404, detail='Resume not found')
        path = os.path.join(UPLOAD_DIR, user.resume_filename)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail='Resume file not found')
        return FileResponse(path, filename=user.resume_filename)
    finally:
        db.close()


@app.put('/employer/{employer_id}/jobs/{job_id}')
def update_employer_job(employer_id: int, job_id: int, data: JobUpdateRequest):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id, Job.employer_id == employer_id).first()
        if not job:
            raise HTTPException(status_code=404, detail='Job not found for this employer')
        values = data.model_dump(exclude_unset=True) if hasattr(data, 'model_dump') else data.dict(exclude_unset=True)
        if 'deadline' in values:
            values['deadline'] = parse_date(values['deadline'])
        if 'vacancy_count' in values and values['vacancy_count'] is not None:
            values['vacancy_count'] = max(1, int(values['vacancy_count']))
        for key, value in values.items():
            setattr(job, key, value)
        job.source = job.source or 'Employer Posted'
        db.commit(); db.refresh(job)
        return {'message': 'Job updated successfully!', 'job': job_to_dict(job)}
    finally:
        db.close()


@app.delete('/employer/{employer_id}/jobs/{job_id}')
def delete_employer_job(employer_id: int, job_id: int):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id, Job.employer_id == employer_id).first()
        if not job:
            raise HTTPException(status_code=404, detail='Job not found for this employer')
        job.is_active = False
        db.commit()
        return {'message': 'Job closed successfully!', 'job_id': job_id, 'is_active': False}
    finally:
        db.close()


@app.post('/employer/{employer_id}/candidate/{candidate_id}/contact')
def contact_candidate(employer_id: int, candidate_id: int, data: CandidateContactRequest):
    db = SessionLocal()
    try:
        employer = db.query(User).filter(User.id == employer_id, User.user_type == 'employer').first()
        candidate = db.query(User).filter(User.id == candidate_id, User.user_type == 'job_seeker').first()
        if not employer or not candidate:
            raise HTTPException(status_code=404, detail='Employer or candidate not found')
        create_notification(
            db, candidate_id, 'Employer contacted you',
            data.message or f'{employer.full_name} is interested in your profile.', 'employer_interest'
        )
        db.commit()
        return {'message': 'Candidate notification sent successfully!'}
    finally:
        db.close()


@app.get('/employer/{employer_id}/candidate/{candidate_id}')
def employer_view_candidate(employer_id: int, candidate_id: int):
    db = SessionLocal()
    try:
        employer = db.query(User).filter(User.id == employer_id, User.user_type == 'employer').first()
        candidate = db.query(User).filter(User.id == candidate_id, User.user_type == 'job_seeker').first()
        if not employer or not candidate:
            raise HTTPException(status_code=404, detail='Employer or candidate not found')
        jobs = db.query(Job).filter(Job.employer_id == employer_id, Job.is_active == True).all()
        matches = []
        for job in jobs:
            m = calculate_candidate_match(candidate, job)
            matches.append({'job': job_to_dict(job), **m})
        matches.sort(key=lambda x: x['match_percentage'], reverse=True)
        return {'candidate': user_to_dict(candidate), 'best_match': matches[0] if matches else None, 'matches': matches}
    finally:
        db.close()


@app.get('/jobs/locations/summary')
def jobs_location_summary():
    db = SessionLocal()
    try:
        jobs = db.query(Job).filter(Job.is_active == True).all()
        states = {}; districts = {}; cities = {}
        for job in jobs:
            s = clean_text(getattr(job, 'state', None))
            d = clean_text(getattr(job, 'district', None))
            c = clean_text(getattr(job, 'city', None))
            if s: states[s] = states.get(s, 0) + 1
            if d: districts[d] = districts.get(d, 0) + 1
            if c: cities[c] = cities.get(c, 0) + 1
        return {'states': states, 'districts': districts, 'cities': cities}
    finally:
        db.close()


@app.post('/job-alerts/process')
def process_job_alerts():
    db = SessionLocal()
    created = 0
    try:
        alerts = db.query(JobAlert).filter(JobAlert.is_active == True).all()
        jobs = db.query(Job).filter(Job.is_active == True).all()
        for alert in alerts:
            for job in jobs[:500]:
                job_text = ' '.join([lower_text(job.title), lower_text(job.company), lower_text(job.category), lower_text(job.description), lower_text(job.skills)])
                if alert.keyword and lower_text(alert.keyword) not in job_text:
                    continue
                loc = ' '.join([lower_text(job.city), lower_text(job.district), lower_text(job.state)])
                if alert.location and lower_text(alert.location) not in loc:
                    continue
                if alert.category and lower_text(alert.category) not in lower_text(job.category):
                    continue
                # create one notification per alert/job/day by checking recent text
                existing = db.query(Notification).filter(Notification.user_id == alert.user_id, Notification.title == 'Job alert', Notification.message.like(f'%{job.title}%')).first()
                if existing:
                    continue
                seeker = db.query(User).filter(User.id == alert.user_id).first()
                if not seeker:
                    continue
                match = calculate_job_match(seeker, job)
                if match['match_percentage'] < int(alert.min_match or 0):
                    continue
                create_notification(db, seeker.id, 'Job alert', f'{job.title} at {job.company} matches your alert ({match["match_percentage"]}%).', 'job_alert')
                created += 1
        db.commit()
        return {'message': 'Job alerts processed successfully!', 'notifications_created': created}
    finally:
        db.close()


@app.get('/admin/source-check')
def source_check():
    return {
        'job_source': REAL_JOBS_API,
        'note': 'Live jobs are imported with their source/apply URL. Verify the employer/source before applying.',
        'government_note': 'Government notifications should be verified on the official recruitment website before applying.'
    }


@app.get("/{page_name}.html")
def serve_html_page(page_name: str):
    safe_name = page_name.replace("/", "")

    allowed_pages = {
        "index",
        "jobs",
        "login",
        "register",
        "dashboard",
        "profile",
        "applications",
        "government",
        "support",
        "employer",
    }

    if safe_name not in allowed_pages:
        raise HTTPException(
            status_code=404,
            detail="Page not found",
        )

    file_path = f"{safe_name}.html"

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"{file_path} not found",
        )

    return FileResponse(
        file_path,
        media_type="text/html",
    )


# =========================================================
# START SERVER DIRECTLY
# =========================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
