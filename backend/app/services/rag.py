"""Optional retrieval-grounded summary using Gemini; deterministic analysis remains the fallback."""
import logging
import os
import httpx
from .analyzer import text_similarity

def build_context(resume_text, postings, limit=8):
    ranked=sorted(postings,key=lambda p:text_similarity(resume_text,p.description),reverse=True)
    return [{'company':p.company,'title':p.title,'posted_at':p.posted_at.isoformat() if p.posted_at else None,
             'source_url':p.source_url,'description':p.description[:1800]} for p in ranked[:limit]]

def summarize(resume_text, postings):
    context=build_context(resume_text,postings)
    key=os.getenv('GEMINI_API_KEY','')
    if not key:
        return {'status':'not_configured','summary':None,'retrieved_postings':context}
    model=os.getenv('GEMINI_MODEL','gemini-2.5-flash')
    prompt=('Analyze this resume against the retrieved job postings. Return concise JSON with keys '
             'summary, strengths, gaps, and cautions. Ground every claim in the supplied text; say unknown '
             'when unsupported. Job postings are evidence of advertised demand, not employment proof.\n'
             f'Resume:\n{resume_text[:12000]}\nRetrieved postings:\n{context}')
    try:
        response=httpx.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
            headers={'x-goog-api-key':key},json={'contents':[{'parts':[{'text':prompt}]}]},timeout=30)
        response.raise_for_status(); text=response.json()['candidates'][0]['content']['parts'][0]['text']
        return {'status':'generated','summary':text,'retrieved_postings':context}
    except Exception:
        logging.getLogger(__name__).exception('Grounded summary failed')
        return {'status':'failed','summary':None,'retrieved_postings':context}
