from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Boolean, Float, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.sql import func
from ..db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(40), nullable=True, unique=True, index=True)
    date_of_birth = Column(Date, nullable=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    phone_verified = Column(Boolean, nullable=False, default=False)
    session_version = Column(Integer, nullable=False, default=0, server_default="0")
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class VerificationCode(Base):
    __tablename__ = "verification_codes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel = Column(String(20), nullable=False)
    destination = Column(String(255), nullable=False)
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    raw_text = Column(Text, nullable=False)
    parsed = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class JobPosting(Base):
    __tablename__ = "job_postings"
    id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False, default="import")
    external_id = Column(String(255), nullable=True)
    company = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    description = Column(Text, nullable=False)
    source_url = Column(Text, nullable=True)
    skills = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external"),)

class Analysis(Base):
    __tablename__ = "analyses"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False)
    target_job_id = Column(Integer, ForeignKey("job_postings.id"), nullable=True)
    overall_score = Column(Float, nullable=False)
    ats_score = Column(Float, nullable=False)
    evidence_score = Column(Float, nullable=False)
    timeline_score = Column(Float, nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
