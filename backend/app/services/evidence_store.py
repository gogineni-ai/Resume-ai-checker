import hashlib
import json
import re
from datetime import datetime, timezone
from sqlalchemy import select, func
from ..models.entities import JobPosting
from ..models.evidence import PostingSnapshot
from .taxonomy import extract_skills, SKILLS

def parse_posted_at(value):
    if not value:
        return None
    # Require a full source-supplied date. Never infer a year from body text.
    if not re.match(r"^\d{4}-\d{2}-\d{2}(?:T|$)", str(value)):
        raise ValueError("Posting date must be ISO YYYY-MM-DD or a timestamp")
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    parsed = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    if parsed > datetime.now(timezone.utc):
        raise ValueError("Posting date cannot be in the future")
    return parsed

def snippet(description, skill):
    for alias in SKILLS.get(skill, [skill]):
        match = re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', description, re.I)
        if match:
            return description[max(0, match.start()-100):match.end()+180].strip()
    return ''

def store_posting(db, row):
    row = dict(row)
    basis = row.pop('date_basis', 'unknown')
    if isinstance(row.get('posted_at'), str):
        row['posted_at'] = parse_posted_at(row['posted_at'])
    if not row.get('posted_at'):
        basis = 'unknown'
    row['skills'] = extract_skills(row['description'])
    existing = db.scalar(select(JobPosting).where(JobPosting.source == row['source'], JobPosting.external_id == row['external_id']))
    if existing is None:
        existing = JobPosting(**row)
        db.add(existing)
        db.flush()
    else:
        for key, value in row.items():
            setattr(existing, key, value)
    digest = hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()
    if not db.scalar(select(PostingSnapshot).where(PostingSnapshot.job_id == existing.id, PostingSnapshot.content_hash == digest)):
        db.add(PostingSnapshot(job_id=existing.id, company=row['company'], source=row['source'], source_url=row['source_url'], title=row['title'], description=row['description'], skills=row['skills'], posted_at=row.get('posted_at'), date_basis=basis, content_hash=digest))
    return existing

def company_evidence(db, company, skill):
    canonical = skill.strip().lower()
    rows = db.scalars(select(PostingSnapshot).where(func.lower(PostingSnapshot.company) == company.strip().lower()).order_by(PostingSnapshot.posted_at.asc(), PostingSnapshot.id.asc())).all()
    hits = [r for r in rows if canonical in r.skills]
    dated = [r for r in hits if r.posted_at]
    earliest = min((r.posted_at for r in dated), default=None)
    return {'company': company, 'skill': canonical, 'earliest_dated_posting': earliest,
            'interpretation': 'Dated job-posting evidence of advertised skill demand; not proof of first technology use or individual employment.',
            'evidence_count': len({r.job_id for r in hits}), 'dated_evidence_count': len({r.job_id for r in dated}),
            'examples': [{'job_id':r.job_id, 'company':r.company, 'title':r.title, 'source':r.source, 'source_url':r.source_url, 'posted_at':r.posted_at, 'collected_at':r.collected_at, 'date_basis':r.date_basis, 'snippet':snippet(r.description,canonical)} for r in hits[:50]]}
