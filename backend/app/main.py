from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, text, inspect, update
from typing import Any
import threading
import asyncio
import os
from contextlib import suppress
import secrets
import hashlib
import httpx
from urllib.parse import urlencode, quote
import hmac
from typing import Literal
from pydantic import Field
from .db import Base, engine, get_db
from .models.entities import User, Resume, JobPosting, Analysis, VerificationCode
from .models.evidence import PostingSnapshot, CollectionRun
from .services.evidence_store import company_evidence, store_posting, parse_posted_at
from .services.parser import extract_text, parse_resume
from .services.analyzer import compare_resume_to_job, analyze_evidence
from .services.ingest import greenhouse_jobs, lever_jobs, parse_refresh_sources, refresh_job_sources
from .services.rag import summarize as rag_summarize
from .services.cross_source import check_consistency
from fastapi.responses import Response
from docx import Document
from io import BytesIO
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen.canvas import Canvas
from .services.taxonomy import extract_skills
from .services.email_service import send_otp_email
from .services.ai_pipeline import generate_ai_insights
from .config import settings
from .auth import hash_password, verify_password, create_token, current_user

app = FastAPI(title="Resume Verifier AI", version="1.0.0")
from .services.gmail_connection import router as gmail_router
app.include_router(gmail_router)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def _database_column_exists(conn, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspect(conn).get_columns(table_name))


def ensure_database_schema() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        if not _database_column_exists(conn, "users", "date_of_birth"):
            conn.execute(text("ALTER TABLE users ADD COLUMN date_of_birth DATE"))
        if not _database_column_exists(conn, "users", "email_verified"):
            conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE"))
        if not _database_column_exists(conn, "users", "phone_verified"):
            conn.execute(text("ALTER TABLE users ADD COLUMN phone_verified BOOLEAN NOT NULL DEFAULT FALSE"))
        if not _database_column_exists(conn, "users", "session_version"):
            conn.execute(text("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"))
        if not _database_column_exists(conn, "verification_codes", "attempts"):
            conn.execute(text("ALTER TABLE verification_codes ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"))

        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_phone ON users(phone) WHERE phone IS NOT NULL"))
        except Exception as index_exc:
            print(f"Phone unique index skipped: {index_exc}")


ensure_database_schema()

_refresh_task = None


def _analysis_summary(result: dict[str, Any]) -> tuple[str, list[str]]:
    missing = [x for x in (result.get("missing_skills") or []) if isinstance(x, str)]
    if missing:
        issue = f"Your resume is missing the strongest role-fit skills: {', '.join(missing[:5])}."
        recommendations = [
            *[f"Add evidence for {skill} in your experience bullets." for skill in missing[:3]],
            "Quantify the impact of your work with metrics and business outcomes.",
            "Add a short project section that mirrors the target job's responsibilities.",
        ]
        return issue, recommendations

    evidence_score = float(result.get("evidence_score") or 0)
    ats_score = float(result.get("ats_score") or 0)
    if evidence_score < 70 or ats_score < 70:
        issue = "The resume is directionally relevant, but the evidence is not strong enough for the target role."
        recommendations = [
            "Tighten the experience section around the target role's core responsibilities.",
            "Replace generic verbs with metrics and technologies from the job description.",
            "Highlight the stack, impact, and ownership in the top three role bullets.",
        ]
        return issue, recommendations

    issue = "The resume is close to the target, but a few details still need to be sharpened for stronger ATS and recruiter fit."
    recommendations = [
        "Trim generic statements and keep only the most relevant wins near the top.",
        "Align your summary with the specific job title and mission.",
        "Add one explicit proof point for each key competency in the role description.",
    ]
    return issue, recommendations


def _build_resume_rewrite(resume_text: str, result: dict[str, Any], target_job: JobPosting | None, tone: str = "confident") -> str:
    skills = [s for s in (result.get("matched_skills") or []) if isinstance(s, str)]
    missing = [s for s in (result.get("missing_skills") or []) if isinstance(s, str)]
    target_skills = []
    if target_job:
        target_skills.extend([s for s in (target_job.skills or []) if isinstance(s, str)])
        target_skills.extend(extract_skills(target_job.description))

    highlight_skills = sorted({*(skills or extract_skills(resume_text)), *(target_skills[:8]), *(missing[:4])})
    tone_label = (tone or "confident").strip().lower() or "confident"
    if tone_label not in {"confident", "professional", "leadership", "friendly"}:
        tone_label = "confident"

    summary = (
        "Software engineer with experience building production services, data pipelines, and customer-focused tools. "
        "Strong background in Python, backend architecture, and shipping scalable, reliable systems with measurable business impact."
    )
    if target_job:
        summary = f"{target_job.title} candidate with experience across backend systems, product delivery, and cross-functional engineering. Skilled in building resilient services, improving workflows, and aligning technical execution with business outcomes."

    skill_line = ", ".join(highlight_skills[:12]) if highlight_skills else "Python, SQL, cloud platforms, backend engineering"
    story = [
        "Professional Summary",
        summary,
        "",
        "Core Skills",
        f"{skill_line}",
        "",
        "Experience",
        "- Built and maintained backend systems using Python, REST APIs, and cloud-native tooling to improve service reliability and delivery speed.",
        "- Partnered with product and engineering teams to translate business requirements into scalable, maintainable software solutions.",
        "- Improved operational efficiency through automation, observability, and streamlined development workflows.",
        "",
        "Selected Achievements",
        "- Delivered production features that increased developer velocity and reduced manual operational work.",
        "- Built resilient data and API workflows that improved quality, scalability, and time-to-value for end users.",
        "- Supported cross-functional delivery by documenting requirements, validating technical tradeoffs, and driving execution.",
        "",
        "Additional Expertise",
        f"- Relevant stack for the role includes {skill_line}.",
        f"- Targeted focus: {', '.join(missing[:5]) if missing else 'stronger alignment with role-specific responsibilities'}.",
    ]
    return "\n".join(story)


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
    try:
        ensure_database_schema()
        print("Database tables initialized")
    except Exception as exc:
        print(f"Database initialization failed: {exc}")

    if settings.auto_refresh_enabled:
        sources = parse_refresh_sources(settings.auto_refresh_sources)
        if sources:
            def refresh_loop():
                import asyncio
                async def runner():
                    while True:
                        try:
                            db = next(get_db())
                            task_result = await refresh_job_sources(db, sources)
                            print(f"Auto-refresh complete: {task_result}")
                            db.close()
                        except Exception as exc:
                            print(f"Auto-refresh failed: {exc}")
                        await asyncio.sleep(max(settings.auto_refresh_interval_minutes, 1) * 60)
                asyncio.run(runner())
            global _refresh_task
            _refresh_task = threading.Thread(target=refresh_loop, daemon=True)
            _refresh_task.start()

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


class ChatMessageIn(BaseModel):
    message: str


class CoachMessageIn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class CoachChatRequest(BaseModel):
    messages: list[CoachMessageIn]
    resume_context: str | None = None
    job_context: str | None = None


class RewriteIn(BaseModel):
    tone: str | None = "confident"
    custom_prompt: str | None = None

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


def _social_provider_settings(provider: str):
    p = provider.lower()
    if p == "google":
        return {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "user_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "scope": "openid email profile",
            "extra": {"access_type": "offline", "prompt": "consent"},
        }
    if p == "microsoft":
        return {
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "redirect_uri": settings.microsoft_redirect_uri,
            "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "user_url": "https://graph.microsoft.com/oidc/userinfo",
            "scope": "openid profile email User.Read",
            "extra": {},
        }
    raise HTTPException(404, "Unsupported provider")


@app.get("/api/auth/social/{provider}/start")
def social_login_start(provider: str):
    cfg = _social_provider_settings(provider)
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise HTTPException(400, f"{provider.title()} OAuth is not configured")
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": cfg["scope"],
        **cfg["extra"],
    }
    return {"auth_url": f"{cfg['auth_url']}?{urlencode(params)}"}


@app.get("/api/auth/social/{provider}/callback")
async def social_login_callback(provider: str, code: str | None = None, db: Session = Depends(get_db)):
    if not code:
        raise HTTPException(400, "Missing OAuth code")
    cfg = _social_provider_settings(provider)
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise HTTPException(400, f"{provider.title()} OAuth is not configured")

    token_payload = {
        "code": code,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": cfg["redirect_uri"],
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        token_res = await client.post(cfg["token_url"], data=token_payload)
        token_res.raise_for_status()
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(400, "Unable to exchange OAuth code")

        user_res = await client.get(cfg["user_url"], headers={"Authorization": f"Bearer {access_token}"})
        user_res.raise_for_status()
        user_info = user_res.json()

    email = (user_info.get("email") or user_info.get("preferred_username") or "").strip().lower()
    if not email:
        raise HTTPException(400, "OAuth account did not return an email")

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(
            name=(user_info.get("name") or email.split("@")[0]).strip() or "OAuth User",
            email=email,
            phone=None,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_token(user.id)
    name = quote(user.name)
    email_q = quote(user.email)
    redirect = f"{settings.frontend_url}/login?auth_success=1&token={token}&name={name}&email={email_q}"
    return RedirectResponse(redirect, status_code=307)


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

@app.post("/api/jobs/import/greenhouse/{board_token}")
async def import_greenhouse(board_token: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    jobs = await greenhouse_jobs(board_token); count=0
    for row in jobs:
        exists = db.scalar(select(JobPosting).where(JobPosting.source==row["source"], JobPosting.external_id==row["external_id"]))
        if not exists: db.add(JobPosting(**row)); count += 1
    db.commit(); return {"imported": count, "seen": len(jobs)}

@app.post("/api/jobs/import/lever/{site}")
async def import_lever(site: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    jobs = await lever_jobs(site); count=0
    for row in jobs:
        exists = db.scalar(select(JobPosting).where(JobPosting.source==row["source"], JobPosting.external_id==row["external_id"]))
        if not exists: db.add(JobPosting(**row)); count += 1
    db.commit(); return {"imported": count, "seen": len(jobs)}


@app.post("/api/jobs/refresh")
async def refresh_jobs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    sources = parse_refresh_sources(settings.auto_refresh_sources)
    if not sources:
        raise HTTPException(400, "No auto-refresh sources configured")
    result = await refresh_job_sources(db, sources)
    return result

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
    overall = None
    if match["ats_score"] is not None and evidence["evidence_score"] is not None and evidence["timeline_score"] is not None:
        overall = round(0.55*match["ats_score"] + 0.30*evidence["evidence_score"] + 0.15*evidence["timeline_score"],1)
    ai_insights = generate_ai_insights(resume.raw_text, target, postings)
    result = {"resume_id":resume.id,"resume_filename":resume.filename,"target_job_id":target_job_id,"target_title":target.title if target else None,"target_company":target.company if target else None,"overall_score":overall,"ai_insights":ai_insights,**match,**evidence}
    overall = result["overall_score"]
    result['rag'] = rag_summarize(resume.raw_text, postings)
    result['cross_source_consistency'] = check_consistency(resume.raw_text, postings)
    row=Analysis(user_id=user.id,resume_id=resume.id,target_job_id=target_job_id,overall_score=overall if overall is not None else 0,ats_score=match["ats_score"] or 0,evidence_score=evidence["evidence_score"] or 0,timeline_score=evidence["timeline_score"] or 0,result=result)
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

@app.post("/api/analyses/{analysis_id}/chat")
def analysis_chat(analysis_id: int, body: ChatMessageIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(Analysis, analysis_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Analysis not found")

    issue, recommendations = _analysis_summary(row.result or {})
    summary = (
        f"The main issue is that your resume is not yet aligned to the target role: {issue} "
        "Use the recommended edits below to strengthen the match and improve ATS readability."
    )
    user_message = (body.message or "").strip()
    if user_message:
        lower_msg = user_message.lower()
        if "missing" in lower_msg or "problem" in lower_msg or "issue" in lower_msg:
            summary = issue
        elif "how" in lower_msg and "improve" in lower_msg:
            summary = "Focus first on the missing skills and rewrite the top experience bullets to mirror the target job's responsibilities."

    return {
        "issues": [issue],
        "issue": issue,
        "summary": summary,
        "recommendations": recommendations,
        "suggestions": recommendations,
    }


@app.post("/api/analyses/{analysis_id}/rewrite")
def analysis_rewrite(analysis_id: int, body: RewriteIn | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(Analysis, analysis_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Analysis not found")

    resume = db.get(Resume, row.resume_id)
    target = db.get(JobPosting, row.target_job_id) if row.target_job_id else None
    tone = (body.tone if body else "confident") or "confident"
    resume_text = resume.raw_text if resume else ""
    rewritten = _build_resume_rewrite(resume_text, row.result or {}, target, tone)
    return {
        "full_resume": rewritten,
        "highlights": [
            "Aligned with the target role",
            "Improved ATS phrasing",
            "Added measurable impact language",
        ],
        "suggested_title": target.title if target else "Relevant Engineering Role",
    }


@app.post("/api/coach/chat")
def coach_chat(body: CoachChatRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    del db, user
    if not body.messages:
        raise HTTPException(400, "At least one chat message is required")

    system_prompt = (
        "You are an expert career and resume coach. You help candidates identify skill gaps, optimize phrasing, "
        "critique impact metrics, and prepare for interviews based on their resume and targeted roles. "
        "Keep answers concise, actionable, and structured with clean bullet points where appropriate."
    )

    resume_context = (body.resume_context or "").strip()
    job_context = (body.job_context or "").strip()

    system_message = {"role": "system", "content": system_prompt}
    context_blocks = []
    if resume_context:
        context_blocks.append({"role": "system", "content": f"Resume context:\n{resume_context}"})
    if job_context:
        context_blocks.append({"role": "system", "content": f"Job context:\n{job_context}"})

    messages = [system_message, *context_blocks, *[{"role": msg.role, "content": msg.content} for msg in body.messages]]

    if not settings.openai_api_key:
        last_user_message = next((m.content for m in reversed(body.messages) if m.role == "user"), "Can you help me improve my resume?")
        return {"reply": f"AI helper is not configured. Based on your last message, focus on: \n- Clarify your strongest impact metrics\n- Add the missing role-specific skills\n- Rewrite the top bullets to align with the target role.\n\nYour prompt: {last_user_message}"}

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        completion = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.4,
            messages=messages,
        )
        reply = completion.choices[0].message.content
        return {"reply": reply or "I could not generate a response. Please try again."}
    except Exception as exc:
        raise HTTPException(500, f"OpenAI coach request failed: {type(exc).__name__}: {exc}") from exc


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
