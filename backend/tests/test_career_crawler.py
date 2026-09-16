import asyncio
from types import SimpleNamespace
from app.services import collector
from app.services.career_crawler import clean_link, crawl_careers


def test_discovery_saves_only_matching_company_and_deduplicates(monkeypatch):
    pages = {
        'https://example.com/robots.txt': 'User-agent: *\nDisallow: /jobs/private',
        'https://example.com/careers': '<a href="/jobs/1">Engineer</a><a href="/jobs/1#apply">Apply</a><a href="/jobs/private">Private job</a><a href="https://other.com/jobs/2">Other job</a>',
        'https://example.com/jobs/1': '<script type="application/ld+json">{"@type":"JobPosting","title":"Python engineer","hiringOrganization":{"name":"Example"},"description":"Python required","datePosted":"2020-01-02"}</script>',
    }
    fetched = []
    async def fetch(url):
        fetched.append(url)
        return pages[url]
    async def sleep(_): pass
    monkeypatch.setattr(collector, 'fetch', fetch)
    monkeypatch.setattr(collector, 'validate_url', lambda url: SimpleNamespace(netloc='example.com'))
    monkeypatch.setattr(asyncio, 'sleep', sleep)
    rows, stats = asyncio.run(crawl_careers({'company':'Example','urls':['https://example.com/careers']}))
    assert len(rows) == 1 and rows[0]['company'] == 'Example'
    assert rows[0]['posted_at'].year == 2020
    assert stats['failed_pages'] == 1
    assert 'https://example.com/jobs/private' not in fetched
    assert all('other.com' not in url for url in fetched)


def test_links_cannot_escape_origin():
    assert clean_link('https://example.com/careers', 'http://example.com/jobs') is None
    assert clean_link('https://example.com/careers', '//private.example/jobs') is None
    assert clean_link('https://example.com/careers', '/jobs/1#apply') == 'https://example.com/jobs/1'
