from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models.evidence import CollectionRun
from app.services import evidence_refresh

def test_refresh_respects_persistent_cooldown(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(evidence_refresh, 'SessionLocal', factory)
    now = datetime.now(timezone.utc)
    assert len(evidence_refresh.due_sources(now)) == len(evidence_refresh.SOURCES)
    with factory() as db:
        for source in evidence_refresh.SOURCES:
            db.add(CollectionRun(source=source['source'], company=source['company'],
                                 status='success', started_at=now))
        db.commit()
    assert evidence_refresh.due_sources(now + timedelta(hours=23)) == []
    assert len(evidence_refresh.due_sources(now + timedelta(days=1))) == len(evidence_refresh.SOURCES)
    engine.dispose()
