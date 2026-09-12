import io, re
from datetime import datetime
from pypdf import PdfReader
from docx import Document
from .taxonomy import extract_skills

DATE_RANGE = re.compile(r"(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)?\s*\d{4})\s*(?:-|–|—|to)\s*(?P<end>Present|Current|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)?\s*\d{4})", re.I)

def extract_text(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if lower.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    return data.decode("utf-8", errors="ignore")

def parse_resume(text: str) -> dict:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    dates = []
    for m in DATE_RANGE.finditer(text):
        dates.append({"start": m.group("start"), "end": m.group("end")})
    sections = {"experience": [], "education": [], "skills": []}
    current = None
    for line in lines:
        l = line.lower().rstrip(":")
        if l in {"experience", "work experience", "professional experience"}: current = "experience"; continue
        if l in {"education", "academic background"}: current = "education"; continue
        if l in {"skills", "technical skills", "technologies"}: current = "skills"; continue
        if current: sections[current].append(line)
    return {
        "skills": extract_skills(text),
        "date_ranges": dates,
        "sections": sections,
        "line_count": len(lines),
    }
