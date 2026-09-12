from app.services.analyzer import compare_resume_to_job

def test_match():
    r = compare_resume_to_job("Python React PostgreSQL", "Need Python and React")
    assert r["ats_score"] > 60
    assert "python" in r["matched_skills"]
