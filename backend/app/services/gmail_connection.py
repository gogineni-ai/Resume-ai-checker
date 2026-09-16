import base64
import hashlib
import secrets
import time
import logging
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import Column, Integer, String, Text, select
from ..db import Base, SessionLocal
from ..auth import current_user, SECRET
from ..config import settings

router = APIRouter(prefix='/api/admin/gmail')

class GmailConnection(Base):
    __tablename__ = 'gmail_sender_connection'
    id = Column(Integer, primary_key=True)
    token = Column(Text, nullable=False)

class GmailSetup(Base):
    __tablename__ = 'gmail_sender_setup'
    state_hash = Column(String(64), primary_key=True)
    verifier = Column(Text, nullable=False)
    expires = Column(Integer, nullable=False)

class HideCallback(logging.Filter):
    def filter(self, record):
        return '/api/admin/gmail/callback' not in record.getMessage()

logging.getLogger('uvicorn.access').addFilter(HideCallback())

def cipher():
    if not settings.gmail_encryption_key:
        raise HTTPException(503, 'Gmail secure storage is not configured')
    return Fernet(settings.gmail_encryption_key.encode())

def administrator(user=Depends(current_user)):
    if SECRET == 'change-this-secret-in-production' or len(SECRET) < 32:
        raise HTTPException(503, 'Secure administrator authentication is not configured')
    if not settings.gmail_admin_email or user.email.lower() != settings.gmail_admin_email.lower() or not user.email_verified:
        raise HTTPException(403, 'Administrator access required')
    return user

@router.get('/status')
def status(user=Depends(administrator)):
    with SessionLocal() as db:
        connected = bool(settings.gmail_refresh_token or db.get(GmailConnection, 1))
    return {'connected': connected, 'active': settings.email_provider == 'gmail',
            'sender': settings.gmail_sender_email}

def stored_token():
    with SessionLocal() as db:
        row = db.get(GmailConnection, 1)
        return cipher().decrypt(row.token.encode()).decode() if row else ''

@router.post('/connect')
def connect(user=Depends(administrator)):
    if not settings.gmail_client_id or not settings.gmail_client_secret or not settings.gmail_sender_email:
        raise HTTPException(503, 'Gmail client configuration is incomplete')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    with SessionLocal() as db:
        db.query(GmailSetup).delete()
        db.add(GmailSetup(state_hash=hashlib.sha256(state.encode()).hexdigest(),
                         verifier=cipher().encrypt(verifier.encode()).decode(), expires=int(time.time())+600))
        db.commit()
    return {'url': 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id':settings.gmail_client_id, 'redirect_uri':settings.gmail_redirect_uri,
        'response_type':'code', 'scope':'openid email https://www.googleapis.com/auth/gmail.send',
        'access_type':'offline', 'prompt':'consent', 'login_hint':settings.gmail_sender_email,
        'state':state, 'code_challenge':challenge, 'code_challenge_method':'S256'})}

@router.get('/callback', response_class=HTMLResponse)
def callback(request: Request):
    state = request.query_params.get('state', '')
    with SessionLocal() as db:
        setup = db.scalar(select(GmailSetup).where(GmailSetup.state_hash == hashlib.sha256(state.encode()).hexdigest()).with_for_update())
        if not setup or setup.expires < time.time():
            raise HTTPException(400, 'Invalid or expired Gmail connection attempt')
        verifier = cipher().decrypt(setup.verifier.encode()).decode()
        db.delete(setup)
        db.commit()
    code = request.query_params.get('code')
    if not code:
        raise HTTPException(400, 'Google authorization was not completed')
    with httpx.Client(timeout=20) as client:
        response = client.post('https://oauth2.googleapis.com/token', data={
            'code':code, 'client_id':settings.gmail_client_id, 'client_secret':settings.gmail_client_secret,
            'redirect_uri':settings.gmail_redirect_uri,'grant_type':'authorization_code','code_verifier':verifier})
        if response.is_error:
            raise HTTPException(400, 'Google authorization exchange failed. Start again.')
        data = response.json()
        identity = client.get('https://openidconnect.googleapis.com/v1/userinfo', headers={'Authorization':'Bearer '+data['access_token']})
        info = identity.json() if identity.is_success else {}
        if info.get('email','').lower() != settings.gmail_sender_email.lower() or info.get('email_verified') is not True:
            raise HTTPException(403, 'Please connect the configured Gmail sender account')
        if 'https://www.googleapis.com/auth/gmail.send' not in data.get('scope','').split() or not data.get('refresh_token'):
            raise HTTPException(400, 'Sending permission and offline access are required')
    with SessionLocal() as db:
        row = db.get(GmailConnection,1)
        if not row:
            row=GmailConnection(id=1,token=''); db.add(row)
        row.token=cipher().encrypt(data['refresh_token'].encode()).decode()
        db.commit()
    return HTMLResponse('<h1>Gmail connected</h1><p>You can close this page and return to Resume Verifier.</p>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
