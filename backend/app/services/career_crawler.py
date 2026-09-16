"""Bounded HTML discovery from operator-configured career sites; no API keys."""
import asyncio
from collections import deque
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
import httpx


def clean_link(base, href):
    url = urlsplit(urljoin(base, href))
    origin = urlsplit(base)
    if url.scheme != 'https' or url.netloc != origin.netloc or url.username or url.password:
        return None
    return urlunsplit((url.scheme, url.netloc, url.path or '/', url.query, ''))


async def crawl_careers(config):
    from .collector import AGENT, fetch, validate_url, jsonld_postings
    seeds = config.get('urls', [])
    if not seeds:
        raise ValueError('Career page seeds are required')
    limit = max(1, min(int(config.get('max_pages', 30)), 100))
    queue = deque(seeds[:limit])
    seen, policies, rows = set(), {}, {}
    failures = 0
    visited = 0
    while queue and len(seen) < limit:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        parsed = validate_url(url)
        origin = f'https://{parsed.netloc}'
        if origin not in policies:
            robots = RobotFileParser()
            try:
                robots.parse((await fetch(origin + '/robots.txt')).splitlines())
            except httpx.HTTPStatusError as error:
                if error.response.status_code != 404:
                    raise
                robots.parse([])
            policies[origin] = robots
        robots = policies[origin]
        if not robots.can_fetch(AGENT, url):
            failures += 1
            continue
        delay = max(1, min(60, robots.crawl_delay(AGENT) or 1))
        # If a site requires a longer delay, skip this source instead of violating it.
        if (robots.crawl_delay(AGENT) or 0) > 60:
            raise ValueError('Site crawl delay exceeds supported limit')
        await asyncio.sleep(delay)
        try:
            html = await fetch(url)
        except httpx.HTTPStatusError as error:
            if error.response.status_code in (401, 403, 429):
                raise
            failures += 1
            continue
        visited += 1
        for row in jsonld_postings(html, url, config['company']):
            rows[row['external_id']] = row
        soup = BeautifulSoup(html, 'html.parser')
        # Discover detail pages and pagination on the same career site only.
        for anchor in soup.find_all('a', href=True):
            link = clean_link(url, anchor['href'])
            hint = (anchor.get_text(' ', strip=True) + ' ' + anchor['href']).lower()
            if link and link not in seen and any(word in hint for word in ('job', 'career', 'position', 'vacanc', 'opening', 'next')):
                if len(queue) < limit * 4:
                    queue.append(link)
    if not rows:
        raise ValueError('No matching structured job postings found; source may require JavaScript or a different seed')
    return list(rows.values()), {'pages': visited, 'failed_pages': failures}
