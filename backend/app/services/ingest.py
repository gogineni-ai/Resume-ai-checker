from datetime import datetime, timezone
import asyncio
import httpx
from bs4 import BeautifulSoup
from .taxonomy import extract_skills


def parse_refresh_sources(value: str):
    if not value or not value.strip():
        return []
    entries = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        if ":" not in item:
            continue
        provider, target = [part.strip() for part in item.split(":", 1)]
        if provider and target:
            entries.append({"provider": provider.lower(), "target": target})
    return entries


async def greenhouse_jobs(board_token: str):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url); r.raise_for_status(); data = r.json()
    out=[]
    for j in data.get("jobs", []):
        desc = BeautifulSoup(j.get("content") or "", "html.parser").get_text(" ")
        out.append({"source":"greenhouse","external_id":str(j["id"]),"company":board_token,"title":j.get("title",""),"location":(j.get("location") or {}).get("name"),"description":desc,"source_url":j.get("absolute_url"),"skills":extract_skills(desc),"posted_at":None,"date_basis":"unknown"})
    return out


async def lever_jobs(site: str):
    url = f"https://api.lever.co/v0/postings/{site}?mode=json"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url); r.raise_for_status(); data = r.json()
    out=[]
    for j in data:
        desc = j.get("descriptionPlain") or BeautifulSoup(j.get("description") or "", "html.parser").get_text(" ")
        for section in j.get("lists") or []:
            desc += " " + (section.get("text") or "") + " " + BeautifulSoup(section.get("content") or "", "html.parser").get_text(" ")
        desc += " " + (j.get("additionalPlain") or BeautifulSoup(j.get("additional") or "", "html.parser").get_text(" "))
        cats=j.get("categories") or {}
        created_at = j.get("createdAt")
        created = datetime.fromtimestamp(created_at / 1000, timezone.utc) if isinstance(created_at, (int,float)) else None
        out.append({"source":"lever","external_id":str(j["id"]),"company":site,"title":j.get("text",""),"location":cats.get("location"),"description":desc,"source_url":j.get("hostedUrl"),"skills":extract_skills(desc),"posted_at":created,"date_basis":"lever_createdAt" if created else "unknown"})
    return out


async def refresh_job_sources(db, sources: list[dict]):
    if not sources:
        return {"imported": 0, "updated": 0, "seen": 0}

    from app.models.entities import JobPosting
    from sqlalchemy import select

    total_imported = 0
    total_updated = 0
    total_seen = 0

    for source in sources:
        provider = source["provider"]
        target = source["target"]
        if provider == "greenhouse":
            rows = await greenhouse_jobs(target)
        elif provider == "lever":
            rows = await lever_jobs(target)
        else:
            continue

        total_seen += len(rows)
        for row in rows:
            existing = db.scalar(select(JobPosting).where(JobPosting.source == row["source"], JobPosting.external_id == row["external_id"]))
            if existing:
                existing.company = row.get("company") or existing.company
                existing.title = row.get("title") or existing.title
                existing.location = row.get("location")
                existing.description = row.get("description") or existing.description
                existing.source_url = row.get("source_url")
                existing.skills = row.get("skills") or existing.skills
                if row.get("posted_at"):
                    existing.posted_at = row["posted_at"]
                total_updated += 1
            else:
                db.add(JobPosting(**row))
                total_imported += 1

    db.commit()
    return {"imported": total_imported, "updated": total_updated, "seen": total_seen}


async def scheduled_refresh_loop(db_factory, sources: list[dict], interval_minutes: int = 60):
    while True:
        try:
            db = db_factory()
            await refresh_job_sources(db, sources)
            db.close()
        except Exception:
            pass
        await asyncio.sleep(max(interval_minutes, 1) * 60)
