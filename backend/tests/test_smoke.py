import csv
import uuid
from pathlib import Path
from sqlalchemy import select

from fastapi.testclient import TestClient
from app.main import app
from app.services.ingest import parse_refresh_sources

client = TestClient(app)


def test_docs_available():
    response = client.get("/docs")
    assert response.status_code == 200


def test_sample_archive_has_diverse_company_data():
    csv_path = Path(__file__).resolve().parents[2] / "sample_data" / "jobs.csv"
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) >= 10
    assert len({row["company"] for row in rows}) >= 6


def test_parse_refresh_sources_handles_multiple_providers():
    sources = parse_refresh_sources("greenhouse:acme, lever:contoso , greenhouse:beta")
    assert sources == [
        {"provider": "greenhouse", "target": "acme"},
        {"provider": "lever", "target": "contoso"},
        {"provider": "greenhouse", "target": "beta"},
    ]


def test_chat_and_rewrite_are_grounded_in_analysis_data():
    email = f"coach-{uuid.uuid4().hex[:8]}@example.com"
    phone = f"555-{uuid.uuid4().hex[:6]}"
    register = client.post(
        "/api/auth/register",
        json={
            "name": "Coach User",
            "email": email,
            "phone": phone,
            "date_of_birth": None,
            "password": "securepass123",
        },
    )
    assert register.status_code == 200, register.text
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    from app.db import SessionLocal
    from app.models.entities import User
    with SessionLocal() as db:
        db.scalar(select(User).where(User.email == email)).email_verified = True
        db.commit()

    resume_text = """
    Python developer with 4 years of software engineering experience.
    Skills: Python, SQL, AWS, Docker, FastAPI.
    Experience: Built APIs and internal tooling for data processing.
    """
    resume = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", resume_text, "text/plain")},
        headers=headers,
    )
    assert resume.status_code == 200, resume.text
    resume_id = resume.json()["id"]

    job = client.post(
        "/api/jobs",
        json={
            "company": "Northstar Labs",
            "title": "Senior Python Engineer",
            "description": "We need Python, Kubernetes, Terraform, distributed systems, FastAPI, and cloud-native engineering experience.",
            "location": "Remote",
            "source_url": "https://example.com/jobs/1",
        },
        headers=headers,
    )
    assert job.status_code == 200, job.text
    job_id = job.json()["id"]

    analysis = client.post(f"/api/analyze/{resume_id}?target_job_id={job_id}", headers=headers)
    assert analysis.status_code == 200, analysis.text
    analysis_id = analysis.json()["analysis_id"]

    chat = client.post(
        f"/api/analyses/{analysis_id}/chat",
        json={"message": "What is the biggest problem with my resume?"},
        headers=headers,
    )
    assert chat.status_code == 200, chat.text
    payload = chat.json()
    assert "issue" in payload or "issues" in payload
    assert "recommendations" in payload or "suggestions" in payload

    rewrite = client.post(
        f"/api/analyses/{analysis_id}/rewrite",
        json={"tone": "confident"},
        headers=headers,
    )
    assert rewrite.status_code == 200, rewrite.text
    text = rewrite.json()["full_resume"]
    assert "Python" in text or "python" in text
    assert "Kubernetes" in text or "kubernetes" in text
