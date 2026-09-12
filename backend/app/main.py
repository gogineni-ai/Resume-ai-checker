from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import select
from .db import Base, engine, get_db
from .models.entities import User, Resume, JobPosting, Analysis
from .services.parser import extract_text, parse_resume
from .services.analyzer import compare_resume_to_job, analyze_evidence
from .services.ingest import greenhouse_jobs, lever_jobs
from .services.taxonomy import extract_skills
from .config import settings
from .auth import hash_password, verify_password, create_token, current_user

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Resume Verifier AI", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    password: str
class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ProfileIn(BaseModel):
    name: str
    phone: str | None = None

class PasswordIn(BaseModel):
    current_password: str
    new_password: str

class JobIn(BaseModel):
    company: str
    title: str
    description: str
    location: str | None = None
    source_url: str | None = None
    posted_at: str | None = None

def public_user(u: User): return {"id":u.id,"name":u.name,"email":u.email,"phone":u.phone}

@app.get("/health")
def health(): return {"ok": True}

@app.post("/api/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if len(body.password) < 8: raise HTTPException(400, "Password must be at least 8 characters")
    email = body.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)): raise HTTPException(409, "An account with this email already exists")
    u = User(name=body.name.strip(), email=email, phone=(body.phone or "").strip() or None, password_hash=hash_password(body.password))
    db.add(u); db.commit(); db.refresh(u)
    return {"access_token": create_token(u.id), "user": public_user(u)}

@app.post("/api/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if not u or not verify_password(body.password, u.password_hash): raise HTTPException(401, "Invalid email or password")
    return {"access_token": create_token(u.id), "user": public_user(u)}

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

    user.name = name
    user.phone = (body.phone or "").strip() or None

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

    db.add(user)
    db.commit()

    return {"ok": True}

@app.post("/api/resumes")
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024: raise HTTPException(413, "File too large")
    text = extract_text(file.filename or "resume.txt", data)
    obj = Resume(user_id=user.id, filename=file.filename or "resume", raw_text=text, parsed=parse_resume(text))
    db.add(obj); db.commit(); db.refresh(obj)
    return {"id": obj.id, "filename": obj.filename, "parsed": obj.parsed}

@app.post("/api/jobs")
def create_job(body: JobIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    j = JobPosting(source="manual", company=body.company, title=body.title, location=body.location, description=body.description, source_url=body.source_url, skills=extract_skills(body.description))
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

@app.get("/api/jobs")
def list_jobs(limit: int = 50, db: Session = Depends(get_db), user: User = Depends(current_user)):
    jobs = db.scalars(select(JobPosting).order_by(JobPosting.id.desc()).limit(min(limit,200))).all()
    return [{"id":j.id,"company":j.company,"title":j.title,"location":j.location,"skills":j.skills,"source":j.source} for j in jobs]

@app.post("/api/analyze/{resume_id}")
def analyze(resume_id: int, target_job_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    resume = db.get(Resume, resume_id)
    if not resume or resume.user_id != user.id: raise HTTPException(404, "Resume not found")
    postings = db.scalars(select(JobPosting)).all()
    evidence = analyze_evidence(resume.raw_text, postings)
    match = {"ats_score":0,"matched_skills":[],"missing_skills":[],"semantic_similarity":0}
    target = None
    if target_job_id:
        target = db.get(JobPosting, target_job_id)
        if not target: raise HTTPException(404, "Job not found")
        match = compare_resume_to_job(resume.raw_text, target.description)
    overall = round(0.55*match["ats_score"] + 0.30*evidence["evidence_score"] + 0.15*evidence["timeline_score"],1)
    result = {"resume_id":resume.id,"resume_filename":resume.filename,"target_job_id":target_job_id,"target_title":target.title if target else None,"target_company":target.company if target else None,"overall_score":overall,**match,**evidence}
    row=Analysis(user_id=user.id,resume_id=resume.id,target_job_id=target_job_id,overall_score=overall,ats_score=match["ats_score"],evidence_score=evidence["evidence_score"],timeline_score=evidence["timeline_score"],result=result)
    db.add(row); db.commit(); db.refresh(row); result["analysis_id"] = row.id
    return result

@app.get("/api/analyses")
def analyses(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Analysis).where(Analysis.user_id==user.id).order_by(Analysis.id.desc()).limit(100)).all()
    return [{"id":r.id,"overall_score":r.overall_score,"ats_score":r.ats_score,"created_at":r.created_at,"result":r.result} for r in rows]

@app.get("/api/analyses/{analysis_id}")
def analysis_detail(analysis_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(Analysis, analysis_id)
    if not row or row.user_id != user.id: raise HTTPException(404, "Analysis not found")
    return {"id":row.id,"created_at":row.created_at,"result":row.result}
