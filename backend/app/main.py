from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, text, inspect, update
import threading
import asyncio
import os
from contextlib import suppress
import secrets
import hashlib
import hmac
from typing import Literal
from pydantic import Field
from .db import Base, engine, get_db
from .models.entities import User, Resume, JobPosting, Analysis, VerificationCode
from .models.evidence import PostingSnapshot, CollectionRun
from .services.evidence_store import company_evidence, store_posting, parse_posted_at
from .services.parser import extract_text, parse_resume
from .services.analyzer import compare_resume_to_job, analyze_evidence
from .services.rag import summarize as rag_summarize
from fastapi.responses import Response
from docx import Document
from io import BytesIO
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen.canvas import Canvas
from .services.ingest import greenhouse_jobs, lever_jobs
from .services.taxonomy import extract_skills
from .services.email_service import send_otp_email
from .config import settings
from .auth import hash_password, verify_password, create_token, current_user

app = FastAPI(title="Resume Verifier AI", version="1.0.0")
from .services.gmail_connection import router as gmail_router
app.include_router(gmail_router)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def start_evidence_refresh():
    # Startup handlers run in registration order; defer until all initialization finishes.
    if os.environ.get('EVIDENCE_COLLECTION_ENABLED') == 'true':
        from .services.evidence_refresh import refresh_loop
        app.state.evidence_task = asyncio.create_task(refresh_loop())

@app.on_event("shutdown")
async def stop_evidence_refresh():
    task = getattr(app.state, 'evidence_task', None)
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

@app.on_event("startup")
def initialize_database():
    Base.metadata.create_all(bind=engine)
    # Existing installations need additive columns before requests are accepted.
    with engine.begin() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("users")}
        for name, ddl in {"session_version": "INTEGER NOT NULL DEFAULT 0", "date_of_birth": "DATE", "email_verified": "BOOLEAN NOT NULL DEFAULT FALSE", "phone_verified": "BOOLEAN NOT NULL DEFAULT FALSE"}.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
        columns = {c["name"] for c in inspect(conn).get_columns("verification_codes")}
        if "attempts" not in columns:
            conn.execute(text("ALTER TABLE verification_codes ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"))

class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    date_of_birth: date | None = None
    password: str
class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ProfileIn(BaseModel):
    name: str
    phone: str | None = None
    date_of_birth: date | None = None

class PasswordIn(BaseModel):
    current_password: str
    new_password: str

class OtpRequestIn(BaseModel):
    channel: Literal["email"]

class OtpVerifyIn(OtpRequestIn):
    code: str = Field(pattern=r"^[0-9]{6}$")

class JobIn(BaseModel):
    company: str
    title: str
    description: str
    location: str | None = None
    source_url: str | None = None
    posted_at: str | None = None

def public_user(u: User): return {"id":u.id,"name":u.name,"email":u.email,"phone":u.phone,"date_of_birth":u.date_of_birth,"email_verified":u.email_verified,"phone_verified":u.phone_verified}

def generate_otp():
    return f"{secrets.randbelow(1000000):06d}"

def hash_otp(code: str):
    return hashlib.sha256(code.encode()).hexdigest()


@app.get("/health")
def health(): return {"ok": True}

@app.post("/api/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if len(body.password) < 8: raise HTTPException(400, "Password must be at least 8 characters")
    if not body.name.strip(): raise HTTPException(400, "Full name is required")
    email = body.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    phone = (body.phone or "").strip() or None
    if phone and db.scalar(select(User).where(User.phone == phone)):
        raise HTTPException(409, "An account with this phone number already exists")
    u = User(
        name=body.name.strip(),
        email=email,
        phone=phone,
        date_of_birth=body.date_of_birth,
        password_hash=hash_password(body.password)
    )
    db.add(u); db.commit(); db.refresh(u)
    sent = True
    try:
        issue_email_code(db, u)
    except HTTPException:
        sent = False
    return {"access_token": create_token(u.id, version=u.session_version), "user": public_user(u), "otp_sent": sent}

@app.post("/api/auth/request-otp")
def request_otp(body: OtpRequestIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return issue_email_code(db, user)

def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def issue_email_code(db, user):
    # Serialize sends and verification for this account in PostgreSQL.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    if user.email_verified:
        return {"ok": True, "already_verified": True}
    now = datetime.now(timezone.utc)
    latest = db.scalar(select(VerificationCode).where(VerificationCode.user_id == user.id, VerificationCode.channel == "email").order_by(VerificationCode.id.desc()))
    if latest and latest.created_at and (now - aware(latest.created_at)).total_seconds() < 60:
        raise HTTPException(429, "Please wait 60 seconds before requesting another code.")
    code = generate_otp()
    try:
        send_otp_email(user.email, code)
    except Exception:
        db.rollback()
        raise HTTPException(503, "Unable to send verification email. Please try again later.")
    db.execute(update(VerificationCode).where(VerificationCode.user_id == user.id, VerificationCode.channel == "email", VerificationCode.used_at.is_(None)).values(used_at=now))
    db.add(VerificationCode(user_id=user.id, channel="email", destination=user.email, code_hash=hash_otp(code), expires_at=now + timedelta(minutes=10), created_at=now))
    db.commit()
    return {"ok": True, "channel": "email", "expires_in_minutes": 10, "retry_after_seconds": 60}

@app.post("/api/auth/verify-otp")
def verify_otp(body: OtpVerifyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    otp = db.scalar(select(VerificationCode).where(VerificationCode.user_id == user.id, VerificationCode.channel == "email").order_by(VerificationCode.id.desc()).with_for_update())
    now = datetime.now(timezone.utc)
    if not otp or otp.used_at or otp.destination != user.email:
        raise HTTPException(400, "No active verification code. Request a new code.")
    if aware(otp.expires_at) <= now:
        raise HTTPException(400, "Verification code expired. Request a new code.")
    if otp.attempts >= 5:
        raise HTTPException(429, "Too many attempts. Request a new code.")
    if not hmac.compare_digest(otp.code_hash, hash_otp(body.code)):
        otp.attempts += 1
        db.commit()
        raise HTTPException(400, "Incorrect verification code.")
    otp.used_at = now
    user.email_verified = True
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": public_user(user)}

def verified_user(user: User = Depends(current_user)):
    if not user.email_verified:
        raise HTTPException(403, "Please verify your email before continuing.")
    return user

@app.post("/api/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if not u or not verify_password(body.password, u.password_hash): raise HTTPException(401, "Invalid email or password")
    return {"access_token": create_token(u.id, version=u.session_version), "user": public_user(u)}

@app.get("/api/auth/me")
def me(user: User = Depends(current_user)): return public_user(user)

@app.put("/api/auth/profile")
def update_profile(
    body: ProfileIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user)
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Full name is required")

    phone = (body.phone or "").strip() or None
    if phone:
        existing_phone = db.scalar(
            select(User).where(User.phone == phone, User.id != user.id)
        )
        if existing_phone:
            raise HTTPException(409, "An account with this phone number already exists")

    user.name = name
    if user.phone != phone: user.phone_verified = False
    user.phone = phone
    if "date_of_birth" in body.model_fields_set:
        user.date_of_birth = body.date_of_birth

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"user": public_user(user)}

@app.put("/api/auth/password")
def update_password(
    body: PasswordIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user)
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")

    if len(body.new_password) < 8:
        raise HTTPException(
            400,
            "New password must be at least 8 characters"
        )

    if body.current_password == body.new_password:
        raise HTTPException(
            400,
            "New password must be different"
        )

    user.password_hash = hash_password(body.new_password)
    user.session_version += 1

    db.add(user)
    db.commit()

    return {"ok": True}

@app.post("/api/resumes")
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(verified_user)):
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024: raise HTTPException(413, "File too large")
    text = extract_text(file.filename or "resume.txt", data)
    obj = Resume(user_id=user.id, filename=file.filename or "resume", raw_text=text, parsed=parse_resume(text))
    db.add(obj); db.commit(); db.refresh(obj)
    return {"id": obj.id, "filename": obj.filename, "parsed": obj.parsed}

@app.post("/api/jobs")
def create_job(body: JobIn, db: Session = Depends(get_db), user: User = Depends(verified_user)):
    j = JobPosting(source="manual", company=body.company, title=body.title, location=body.location, description=body.description, source_url=body.source_url, posted_at=parse_posted_at(body.posted_at), skills=extract_skills(body.description))
    db.add(j); db.commit(); db.refresh(j)
    return {"id": j.id, "skills": j.skills}

@app.get("/api/jobs")
def list_jobs(limit: int = 50, db: Session = Depends(get_db), user: User = Depends(verified_user)):
    jobs = db.scalars(select(JobPosting).order_by(JobPosting.id.desc()).limit(min(limit,200))).all()
    return [{"id":j.id,"company":j.company,"title":j.title,"location":j.location,"skills":j.skills,"source":j.source} for j in jobs]

@app.post("/api/analyze/{resume_id}")
def analyze(resume_id: int, target_job_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(verified_user)):
    resume = db.get(Resume, resume_id)
    if not resume or resume.user_id != user.id: raise HTTPException(404, "Resume not found")
    postings = db.scalars(select(JobPosting).where(JobPosting.source != "manual")).all()
    evidence = analyze_evidence(resume.raw_text, postings)
    match = {"ats_score":0,"matched_skills":[],"missing_skills":[],"semantic_similarity":0}
    target = None
    if target_job_id:
        target = db.get(JobPosting, target_job_id)
        if not target: raise HTTPException(404, "Job not found")
        match = compare_resume_to_job(resume.raw_text, target.description)
    overall = match["ats_score"] if target else evidence["evidence_score"]
    result = {"resume_id":resume.id,"resume_filename":resume.filename,"target_job_id":target_job_id,"target_title":target.title if target else None,"target_company":target.company if target else None,"overall_score":overall,**match,**evidence}
    result['rag'] = rag_summarize(resume.raw_text, postings)
    row=Analysis(user_id=user.id,resume_id=resume.id,target_job_id=target_job_id,overall_score=overall or 0,ats_score=match["ats_score"] or 0,evidence_score=evidence["evidence_score"],timeline_score=evidence["timeline_score"] or 0,result=result)
    db.add(row); db.commit(); db.refresh(row); result["analysis_id"] = row.id
    return result

@app.get("/api/analyses")
def analyses(db: Session = Depends(get_db), user: User = Depends(verified_user)):
    rows = db.scalars(select(Analysis).where(Analysis.user_id==user.id).order_by(Analysis.id.desc()).limit(100)).all()
    return [{"id":r.id,"overall_score":r.overall_score,"ats_score":r.ats_score,"created_at":r.created_at,"result":r.result} for r in rows]

@app.get("/api/analyses/{analysis_id}")
def analysis_detail(analysis_id: int, db: Session = Depends(get_db), user: User = Depends(verified_user)):
    row = db.get(Analysis, analysis_id)
    if not row or row.user_id != user.id: raise HTTPException(404, "Analysis not found")
    return {"id":row.id,"created_at":row.created_at,"result":row.result}

def _owned_analysis(analysis_id, db, user):
    row=db.get(Analysis,analysis_id)
    if not row or row.user_id != user.id: raise HTTPException(404,'Analysis not found')
    return row

@app.get('/api/analyses/{analysis_id}/report.docx')
def report_docx(analysis_id:int, db:Session=Depends(get_db), user:User=Depends(verified_user)):
    row=_owned_analysis(analysis_id,db,user); result=row.result
    doc=Document(); doc.add_heading('Resume Verifier AI Report',0); doc.add_paragraph(result.get('resume_filename',''))
    doc.add_heading('Scores',1); doc.add_paragraph(f"Overall: {result.get('overall_score')}; Skills match: {result.get('skill_match_score')}; Evidence: {result.get('evidence_score')}")
    doc.add_heading('Matched skills',1); doc.add_paragraph(', '.join(result.get('matched_skills',[])) or 'None')
    doc.add_heading('Missing skills',1); doc.add_paragraph(', '.join(result.get('missing_skills',[])) or 'None')
    doc.add_heading('Evidence and limitations',1); doc.add_paragraph(result.get('evidence_note','Job postings indicate advertised demand and do not verify employment.'))
    if result.get('rag',{}).get('summary'): doc.add_heading('Grounded AI review',1); doc.add_paragraph(result['rag']['summary'])
    data=BytesIO(); doc.save(data)
    return Response(data.getvalue(),media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers={'Content-Disposition':f'attachment; filename="resume-analysis-{analysis_id}.docx"'})

@app.get('/api/analyses/{analysis_id}/report.pdf')
def report_pdf(analysis_id:int, db:Session=Depends(get_db), user:User=Depends(verified_user)):
    row=_owned_analysis(analysis_id,db,user); result=row.result
    data=BytesIO(); canvas=Canvas(data,pagesize=LETTER); _, height=LETTER; y=height-54
    def line(value=''):
        nonlocal y
        for part in str(value).splitlines() or ['']:
            if y < 54: canvas.showPage(); y=height-54
            canvas.drawString(54,y,part[:110]); y-=15
    canvas.setFont('Helvetica-Bold',18); line('Resume Verifier AI Report'); canvas.setFont('Helvetica',10)
    line(result.get('resume_filename','')); line('Scores')
    line(f"Overall: {result.get('overall_score')}; Skills match: {result.get('skill_match_score')}; Evidence: {result.get('evidence_score')}")
    line('Matched skills: '+(', '.join(result.get('matched_skills',[])) or 'None'))
    line('Missing skills: '+(', '.join(result.get('missing_skills',[])) or 'None'))
    line('Evidence and limitations: '+result.get('evidence_note','Job postings indicate advertised demand and do not verify employment.'))
    if result.get('rag',{}).get('summary'): line('Grounded AI review: '+result['rag']['summary'])
    canvas.save(); return Response(data.getvalue(),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="resume-analysis-{analysis_id}.pdf"'})

@app.get("/api/evidence")
def evidence_lookup(company: str, skill: str, db: Session = Depends(get_db), user: User = Depends(verified_user)):
    if not company.strip() or not skill.strip(): raise HTTPException(400, "Company and skill are required")
    return company_evidence(db, company, skill)

@app.get("/api/evidence/collection-status")
def evidence_status(db: Session = Depends(get_db), user: User = Depends(verified_user)):
    runs=db.scalars(select(CollectionRun).order_by(CollectionRun.id.desc()).limit(20)).all()
    return [{"source":r.source,"company":r.company,"status":r.status,"count":r.count,"finished_at":r.finished_at} for r in runs]

class ResetRequestIn(BaseModel):
    email: EmailStr

class ResetPasswordIn(ResetRequestIn):
    code: str = Field(pattern=r"^[0-9]{6}$")
    password: str = Field(min_length=8, max_length=256)

@app.post("/api/auth/forgot-password")
def forgot_password(body: ResetRequestIn, db: Session = Depends(get_db)):
    message={"message":"If an account exists, a password reset code will be sent. Check your inbox and spam folder."}
    user=db.scalar(select(User).where(User.email==body.email.lower().strip()).with_for_update())
    if not user: return message
    now=datetime.now(timezone.utc)
    latest=db.scalar(select(VerificationCode).where(VerificationCode.user_id==user.id,VerificationCode.channel=='password_reset').order_by(VerificationCode.id.desc()))
    if latest and (now-aware(latest.created_at)).total_seconds()<60: return message
    code=generate_otp()
    try: send_otp_email(user.email,code,purpose='password reset')
    except Exception: return message
    db.execute(update(VerificationCode).where(VerificationCode.user_id==user.id,VerificationCode.channel=='password_reset',VerificationCode.used_at.is_(None)).values(used_at=now))
    db.add(VerificationCode(user_id=user.id,channel='password_reset',destination=user.email,code_hash=hash_otp(code),created_at=now,expires_at=now+timedelta(minutes=10)))
    db.commit()
    return message

@app.post("/api/auth/reset-password")
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    user=db.scalar(select(User).where(User.email==body.email.lower().strip()).with_for_update())
    error='Invalid or expired reset code.'
    if not user: raise HTTPException(400,error)
    otp=db.scalar(select(VerificationCode).where(VerificationCode.user_id==user.id,VerificationCode.channel=='password_reset').order_by(VerificationCode.id.desc()).with_for_update())
    now=datetime.now(timezone.utc)
    if not otp or otp.used_at or aware(otp.expires_at)<=now or otp.attempts>=5: raise HTTPException(400,error)
    if not hmac.compare_digest(otp.code_hash,hash_otp(body.code)):
        otp.attempts+=1;db.commit();raise HTTPException(400,error)
    user.password_hash=hash_password(body.password);user.session_version+=1;otp.used_at=now;db.commit()
    return {"ok":True}
