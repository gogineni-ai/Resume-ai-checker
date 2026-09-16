from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from ..db import Base

class PostingSnapshot(Base):
    """Immutable observed versions; collection time is never a posting date."""
    __tablename__ = "posting_snapshots"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("job_postings.id"), nullable=False, index=True)
    company = Column(String(255), nullable=False, index=True)
    source = Column(String(50), nullable=False)
    source_url = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    skills = Column(JSON, nullable=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    date_basis = Column(String(60), nullable=False)
    collected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_hash = Column(String(64), nullable=False)
    __table_args__ = (UniqueConstraint("job_id", "content_hash", name="uq_posting_snapshot"),)

class CollectionRun(Base):
    __tablename__ = "collection_runs"
    id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False)
    company = Column(String(255), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    status = Column(String(30), nullable=False, default="running")
    count = Column(Integer, nullable=False, default=0)
    error = Column(Text)
