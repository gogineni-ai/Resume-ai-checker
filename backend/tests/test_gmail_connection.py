from types import SimpleNamespace
from urllib.parse import urlparse, parse_qs

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.services import gmail_connection as gmail


@pytest.fixture
def client(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    gmail.GmailSetup.__table__.create(engine)
    gmail.GmailConnection.__table__.create(engine)
    monkeypatch.setattr(gmail, 'SessionLocal', sessionmaker(bind=engine))
    for key, value in {'gmail_encryption_key': Fernet.generate_key().decode(),
                       'gmail_client_id': 'fixture', 'gmail_client_secret': 'fixture',
                       'gmail_sender_email': 'sender@example.com'}.items():
        monkeypatch.setattr(gmail.settings, key, value)
    app = FastAPI()
    app.include_router(gmail.router)
    app.dependency_overrides[gmail.administrator] = lambda: SimpleNamespace(id=1)
    yield TestClient(app)
    engine.dispose()


def test_setup_expires_and_cannot_be_replayed(client):
    response = client.post('/api/admin/gmail/connect')
    query = parse_qs(urlparse(response.json()['url']).query)
    assert query['code_challenge_method'] == ['S256']
    state = query['state'][0]
    with gmail.SessionLocal() as db:
        row = db.query(gmail.GmailSetup).one()
        assert row.state_hash != state
        assert row.verifier != gmail.cipher().decrypt(row.verifier.encode()).decode()
    cancelled = client.get('/api/admin/gmail/callback', params={'state': state})
    assert cancelled.status_code == 400
    assert 'not completed' in cancelled.json()['detail']
    replay = client.get('/api/admin/gmail/callback', params={'state': state, 'code': 'fixture'})
    assert replay.status_code == 400
    assert 'Invalid or expired' in replay.json()['detail']


def test_expired_setup_fails_before_token_exchange(client):
    query = parse_qs(urlparse(client.post('/api/admin/gmail/connect').json()['url']).query)
    with gmail.SessionLocal() as db:
        db.query(gmail.GmailSetup).one().expires = 0
        db.commit()
    assert client.get('/api/admin/gmail/callback', params={'state': query['state'][0], 'code': 'fixture'}).status_code == 400


def test_admin_requires_secure_auth_and_verified_matching_account(monkeypatch):
    monkeypatch.setattr(gmail, 'SECRET', 'change-this-secret-in-production')
    with pytest.raises(HTTPException) as failure:
        gmail.administrator(SimpleNamespace(email='owner@example.com', email_verified=True))
    assert failure.value.status_code == 503
    monkeypatch.setattr(gmail, 'SECRET', 'x' * 40)
    monkeypatch.setattr(gmail.settings, 'gmail_admin_email', 'owner@example.com')
    for email, verified in [('other@example.com', True), ('owner@example.com', False)]:
        with pytest.raises(HTTPException) as failure:
            gmail.administrator(SimpleNamespace(email=email, email_verified=verified))
        assert failure.value.status_code == 403
