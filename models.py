from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey
)

from database import Base


# =========================================================
# USER
# =========================================================

class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    full_name = Column(
        String(150),
        nullable=False
    )

    email = Column(
        String(200),
        unique=True,
        index=True,
        nullable=False
    )

    mobile = Column(
        String(20),
        unique=True,
        nullable=True
    )

    password = Column(
        String(255),
        nullable=False
    )

    user_type = Column(
        String(30),
        default="job_seeker",
        nullable=False
    )

    qualification = Column(
        String(250),
        nullable=True
    )

    skills = Column(
        Text,
        nullable=True
    )

    experience = Column(
        String(100),
        nullable=True
    )

    location = Column(
        String(200),
        nullable=True
    )

    state = Column(
        String(150),
        nullable=True
    )

    salary = Column(
        String(100),
        nullable=True
    )

    job_categories = Column(
        Text,
        nullable=True
    )

    resume_filename = Column(
        String(300),
        nullable=True
    )

    reset_otp = Column(
        String(10),
        nullable=True
    )

    reset_otp_expires = Column(
        DateTime,
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


# =========================================================
# JOB
# =========================================================

class Job(Base):
    __tablename__ = "jobs"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    title = Column(
        String(250),
        nullable=False
    )

    company = Column(
        String(250),
        nullable=False
    )

    category = Column(
        String(120),
        nullable=False
    )

    job_type = Column(
        String(80),
        nullable=True
    )

    state = Column(
        String(150),
        nullable=True
    )

    district = Column(
        String(150),
        nullable=True
    )

    city = Column(
        String(150),
        nullable=True
    )

    description = Column(
        Text,
        nullable=True
    )

    qualification = Column(
        String(300),
        nullable=True
    )

    skills = Column(
        Text,
        nullable=True
    )

    experience = Column(
        String(100),
        nullable=True
    )

    salary = Column(
        String(150),
        nullable=True
    )

    vacancy_count = Column(
        Integer,
        default=1
    )

    deadline = Column(
        String(100),
        nullable=True
    )

    source = Column(
        String(250),
        nullable=True
    )

    source_url = Column(
        String(1000),
        nullable=True
    )

    employer_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    is_active = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


# =========================================================
# APPLICATION
# =========================================================

class Application(Base):
    __tablename__ = "applications"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    job_id = Column(
        Integer,
        ForeignKey("jobs.id"),
        nullable=False
    )

    status = Column(
        String(50),
        default="Applied",
        nullable=False
    )

    cover_letter = Column(
        Text,
        nullable=True
    )

    message = Column(
        Text,
        nullable=True
    )

    applied_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


# =========================================================
# GOVERNMENT JOB
# =========================================================

class GovernmentJob(Base):
    __tablename__ = "government_jobs"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    title = Column(
        String(300),
        nullable=False
    )

    organization = Column(
        String(300),
        nullable=True
    )

    state = Column(
        String(150),
        nullable=True
    )

    qualification = Column(
        String(300),
        nullable=True
    )

    description = Column(
        Text,
        nullable=True
    )

    exam_date = Column(
        String(100),
        nullable=True
    )

    last_date = Column(
        String(100),
        nullable=True
    )

    notification_url = Column(
        String(1000),
        nullable=True
    )

    source = Column(
        String(300),
        nullable=True
    )

    is_active = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


# =========================================================
# NOTIFICATION
# =========================================================

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    title = Column(
        String(300),
        nullable=False
    )

    message = Column(
        Text,
        nullable=False
    )

    notification_type = Column(
        String(100),
        nullable=True
    )

    is_read = Column(
        Boolean,
        default=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )