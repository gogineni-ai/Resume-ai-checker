"""Cross-source consistency checks over the application's archived job evidence."""
from collections import defaultdict
from .taxonomy import extract_skills

def check_consistency(resume_text: str, postings: list) -> dict:
    skills = extract_skills(resume_text)
    rows = []
    for skill in skills:
        by_source = defaultdict(list)
        for posting in postings:
            if skill in (posting.skills or []):
                by_source[posting.source or "unknown"].append(posting)
        sources = sorted(by_source)
        examples = [{"company": p.company, "title": p.title, "source": p.source,
                     "year": p.posted_at.year if p.posted_at else None,
                     "source_url": p.source_url} for p in [p for group in by_source.values() for p in group[:2]][:6]]
        rows.append({"skill": skill, "source_count": len(sources), "sources": sources,
                     "posting_count": sum(len(v) for v in by_source.values()), "examples": examples,
                     "status": "consistent across sources" if len(sources) >= 2 else ("single-source evidence" if sources else "no evidence")})
    assessed = bool(rows)
    consistent = sum(r["status"] == "consistent across sources" for r in rows)
    return {"agent": "cross-source-consistency", "assessed": assessed,
            "score": round(100 * consistent / len(rows), 1) if rows else 0,
            "note": "Compares archived postings from different sources. It indicates market-demand consistency, not proof of employment or skill proficiency.",
            "skills": rows}
