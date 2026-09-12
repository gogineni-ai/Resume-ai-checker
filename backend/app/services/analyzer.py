from collections import Counter
from datetime import datetime
from dateutil import parser as dtparser
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .taxonomy import extract_skills

# Approximate public-release / broad-availability years. Keep editable and evidence-linked in production.
TECH_START_YEAR = {
    "python": 1991, "java": 1995, "javascript": 1995, "react": 2013, "angular": 2010,
    "vue": 2014, "node.js": 2009, "typescript": 2012, "next.js": 2016, "fastapi": 2018,
    "django": 2005, "flask": 2010, "graphql": 2015, "docker": 2013, "kubernetes": 2014,
    "terraform": 2014, "github actions": 2019, "aws": 2006, "gcp": 2008, "azure": 2010,
    "snowflake": 2014, "pytorch": 2016, "tensorflow": 2015,
}

def text_similarity(a: str, b: str) -> float:
    if not a.strip() or not b.strip(): return 0.0
    X = TfidfVectorizer(stop_words="english", ngram_range=(1,2), max_features=8000).fit_transform([a,b])
    return float(cosine_similarity(X[0:1], X[1:2])[0][0])

def compare_resume_to_job(resume_text: str, job_text: str) -> dict:
    rskills = set(extract_skills(resume_text)); jskills = set(extract_skills(job_text))
    matched = sorted(rskills & jskills); missing = sorted(jskills - rskills)
    skill_score = 100.0 if not jskills else 100 * len(matched) / len(jskills)
    sim = 100 * text_similarity(resume_text, job_text)
    ats = round(0.7 * skill_score + 0.3 * sim, 1)
    return {"ats_score": ats, "matched_skills": matched, "missing_skills": missing, "semantic_similarity": round(sim,1)}

def evidence_for_skill(skill: str, postings: list, claimed_start_year: int | None = None) -> dict:
    hits = []
    for p in postings:
        if skill in (p.skills or []):
            year = p.posted_at.year if p.posted_at else None
            hits.append({"job_id": p.id, "company": p.company, "title": p.title, "year": year, "source_url": p.source_url})
    years = [h["year"] for h in hits if h["year"]]
    first_seen = min(years) if years else None
    release_year = TECH_START_YEAR.get(skill)
    conflict = bool(claimed_start_year and release_year and claimed_start_year < release_year)
    if conflict: status = "timeline conflict"
    elif hits: status = "supported"
    elif release_year and claimed_start_year and claimed_start_year >= release_year: status = "plausible"
    else: status = "weak evidence"
    return {"skill": skill, "status": status, "release_year": release_year, "first_seen_in_archive": first_seen, "evidence_count": len(hits), "examples": hits[:5]}

def analyze_evidence(resume_text: str, postings: list) -> dict:
    skills = extract_skills(resume_text)
    evidence = [evidence_for_skill(s, postings) for s in skills]
    if not evidence:
        return {"evidence_score": 0, "timeline_score": None, "skills": []}
    supported = sum(e["status"] in {"supported", "plausible"} for e in evidence)
    conflicts = sum(e["status"] == "timeline conflict" for e in evidence)
    return {
        "evidence_score": round(100 * supported / len(evidence), 1),
        "timeline_score": None,
        "timeline_note": "Not assessed: employment dates are not extracted or verified.",
        "evidence_note": "Job postings support advertised skill demand, not personal employment or first technology use.",
        "skills": evidence,
    }
