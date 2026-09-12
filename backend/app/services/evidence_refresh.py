"""Refresh a small, operator-owned public board list while the web service is awake."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from ..db import SessionLocal
from ..models.evidence import CollectionRun
from .collector import run_collection

SOURCES = [
    {'source': 'lever', 'board': 'highstreetit', 'company': 'Highstreet'},
    {'source': 'greenhouse', 'board': 'sphereit', 'company': 'Sphere IT Consultants DWC LLC'},
    {'source': 'lever', 'board': 'ciandt', 'company': 'CI&T'},
    {'source': 'greenhouse', 'board': 'nice', 'company': 'NICE'},
    {'source': 'greenhouse', 'board': 'accenturefederalservices', 'company': 'Accenture Federal Services'},
    {'source': 'greenhouse', 'board': 'neweratech', 'company': 'New Era Technology'},
]

def due_sources(now=None):
    now = now or datetime.now(timezone.utc)
    due = []
    with SessionLocal() as db:
        for source in SOURCES:
            last = db.scalar(select(CollectionRun).where(
                CollectionRun.source == source['source'],
                CollectionRun.company == source['company'],
            ).order_by(CollectionRun.id.desc()))
            stamp = last.started_at if last else None
            if stamp and stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            delay = timedelta(days=1) if last and last.status == 'success' else timedelta(hours=1)
            if stamp is None or now - stamp >= delay:
                due.append(source)
    return due

async def refresh_loop():
    while True:
        try:
            await run_collection(due_sources())
        except Exception:
            logging.getLogger(__name__).error('Evidence refresh failed; retrying in one hour')
        await asyncio.sleep(3600)
