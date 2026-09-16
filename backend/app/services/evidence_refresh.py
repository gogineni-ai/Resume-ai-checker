"""Refresh a small, operator-owned public board list while the web service is awake."""
import asyncio
import logging
import json
import os
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
        extra = json.loads(os.environ.get('CAREER_HTML_SOURCES', '[]'))
        if not isinstance(extra, list) or len(extra) > 500:
            raise ValueError('CAREER_HTML_SOURCES must contain at most 500 career sites')
        for source in SOURCES + [dict(item, source='career_html') for item in extra]:
            if not source.get('enabled', True):
                continue
            last = db.scalar(select(CollectionRun).where(
                CollectionRun.source == source['source'],
                CollectionRun.company == source['company'],
            ).order_by(CollectionRun.id.desc()))
            stamp = last.started_at if last else None
            if stamp and stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            delay = timedelta(days=1) if last and last.status == 'success' else timedelta(hours=1)
            if stamp is None or now - stamp >= delay:
                due.append((stamp or datetime.min.replace(tzinfo=timezone.utc), source))
    # Oldest/never-checked sources first, so failing sites cannot starve others.
    return [source for _, source in sorted(due, key=lambda item: item[0])[:20]]

async def refresh_loop():
    while True:
        try:
            await run_collection(due_sources())
        except Exception:
            logging.getLogger(__name__).error('Evidence refresh failed; retrying in one hour')
        await asyncio.sleep(3600)
