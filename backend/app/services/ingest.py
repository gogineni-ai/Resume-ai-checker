from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from .taxonomy import extract_skills

async def greenhouse_jobs(board_token: str):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url); r.raise_for_status(); data = r.json()
    out=[]
    for j in data.get("jobs", []):
        desc = BeautifulSoup(j.get("content") or "", "html.parser").get_text(" ")
        out.append({"source":"greenhouse","external_id":str(j["id"]),"company":board_token,"title":j.get("title",""),"location":(j.get("location") or {}).get("name"),"description":desc,"source_url":j.get("absolute_url"),"skills":extract_skills(desc)})
    return out

async def lever_jobs(site: str):
    url = f"https://api.lever.co/v0/postings/{site}?mode=json"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url); r.raise_for_status(); data = r.json()
    out=[]
    for j in data:
        desc = j.get("descriptionPlain") or BeautifulSoup(j.get("description") or "", "html.parser").get_text(" ")
        cats=j.get("categories") or {}
        out.append({"source":"lever","external_id":str(j["id"]),"company":site,"title":j.get("text",""),"location":cats.get("location"),"description":desc,"source_url":j.get("hostedUrl"),"skills":extract_skills(desc)})
    return out
