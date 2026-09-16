"""Operator-configured collectors. No public endpoint accepts arbitrary fetch URLs."""
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup
from ..db import SessionLocal
from ..models.evidence import CollectionRun
from .evidence_store import store_posting, parse_posted_at
from .ingest import greenhouse_jobs, lever_jobs

AGENT = 'ResumeEvidenceCollector/1.0'
PARTNER_SOURCES = {'linkedin', 'indeed', 'monster', 'dice'}

def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Source must be a public HTTPS URL without embedded credentials')
    for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(item[4][0]).is_global:
            raise ValueError('Private network sources are not supported')
    return parsed

async def fetch(url, token=None):
    validate_url(url)
    headers={'User-Agent':AGENT}
    if token: headers['Authorization']=f'Bearer {token}'
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        async with client.stream('GET', url, headers=headers) as response:
            response.raise_for_status()
            chunks=[]; size=0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 10*1024*1024: raise ValueError('Source response exceeds 10MB')
                chunks.append(chunk)
            return b''.join(chunks).decode('utf-8')

def jsonld_postings(html, url, company):
    soup=BeautifulSoup(html,'html.parser')
    def walk(obj):
        if isinstance(obj,list):
            for item in obj: yield from walk(item)
        elif isinstance(obj,dict):
            kind=obj.get('@type',[])
            if kind=='JobPosting' or isinstance(kind,list) and 'JobPosting' in kind: yield obj
            for key in ('@graph','itemListElement','item'):
                if key in obj: yield from walk(obj[key])
    out=[]
    for script in soup.find_all('script',type='application/ld+json'):
        try: data=json.loads(script.string or script.get_text())
        except ValueError: continue
        for job in walk(data):
            org=job.get('hiringOrganization') or {}
            name=org.get('name','').strip()
            if name.casefold()!=company.casefold(): continue
            source_url=urljoin(url,job.get('url') or url)
            if urlparse(source_url).scheme!='https': continue
            identifier=job.get('identifier') or source_url
            if isinstance(identifier,dict): identifier=identifier.get('value') or source_url
            out.append({'source':'company','external_id':hashlib.sha256((company+str(identifier)).encode()).hexdigest(), 'company':company,'title':job.get('title') or 'Untitled role','description':BeautifulSoup(job.get('description') or '', 'html.parser').get_text(' ',strip=True),'source_url':source_url,'posted_at':parse_posted_at(job.get('datePosted')),'date_basis':'source_datePosted'})
    return out

async def collect_source(config):
    source=config['source']; company=config['company'].strip()
    if source == 'career_html':
        from .career_crawler import crawl_careers
        rows, _ = await crawl_careers(config)
        return rows
    if source in ('greenhouse','lever'):
        board=config['board']
        if not re.fullmatch(r'[A-Za-z0-9_-]+',board): raise ValueError('Invalid board identifier')
        rows=await (greenhouse_jobs(board) if source=='greenhouse' else lever_jobs(board))
        for row in rows:
            row['company']=company
            row['external_id']=board+':'+row['external_id']
            # Greenhouse's updated_at is not an original posting date. Lever's
            # createdAt is retained by the adapter as a source creation date.
            if source == 'greenhouse':
                row['posted_at']=None; row['date_basis']='unknown'
        return rows
    if source=='company':
        if not config.get('collection_permitted'): raise ValueError('Confirm site collection permission in source configuration')
        rows=[]
        for url in config.get('urls',[])[:100]:
            parsed=validate_url(url)
            robots_url=f'{parsed.scheme}://{parsed.netloc}/robots.txt'
            robots=RobotFileParser(); robots.parse((await fetch(robots_url)).splitlines())
            if not robots.can_fetch(AGENT,url): raise ValueError('Collection disallowed by robots.txt')
            rows.extend(jsonld_postings(await fetch(url),url,company))
            await asyncio.sleep(1)
        return rows
    if source in PARTNER_SOURCES or source=='licensed_feed':
        if not config.get('licensed_feed_url') or not config.get('collection_permitted'):
            raise ValueError('An authorized job-data feed is required for this source')
        token=os.environ.get(config.get('token_env','')) or None
        data=json.loads(await fetch(config['licensed_feed_url'],token))
        rows=[]
        for item in data['jobs']:
            if item['company'].strip().casefold()!=company.casefold(): continue
            url=item['source_url']
            if urlparse(url).scheme!='https': raise ValueError('Source URL must use HTTPS')
            rows.append({'source':source,'external_id':company+':'+str(item['id']),'company':company,'title':item['title'],'description':item['description'],'source_url':url,'posted_at':parse_posted_at(item.get('posted_at')),'date_basis':'licensed_source_date'})
        return rows
    raise ValueError('Unsupported source')

async def run_collection(configs):
    results=[]
    for config in configs:
        if not config.get('enabled',True): continue
        with SessionLocal() as db:
            run=CollectionRun(source=config['source'],company=config['company'])
            db.add(run); db.commit(); run_id=run.id
            try:
                rows=await collect_source(config)
                for row in rows: store_posting(db,row)
                run.status='success'; run.count=len(rows)
            except Exception as exc:
                db.rollback();run=db.get(CollectionRun,run_id);run.status='failed'
                # Keep tokens, URLs with query credentials, and provider bodies out of logs.
                run.error=type(exc).__name__ + ': collection failed; check source configuration and access.'
            run.finished_at=datetime.now(timezone.utc);db.commit()
            results.append({'id':run.id,'source':run.source,'company':run.company,'status':run.status,'count':run.count})
        await asyncio.sleep(1)
    return results
