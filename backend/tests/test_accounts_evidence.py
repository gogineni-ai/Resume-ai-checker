import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import main
from app.db import Base, get_db
from app.models.entities import User, VerificationCode
from app.models.evidence import PostingSnapshot
from app.services.evidence_store import store_posting, company_evidence
from app.services.collector import jsonld_postings

@pytest.fixture
def ctx(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    def get_test_db():
        with factory() as db: yield db
    main.app.dependency_overrides[get_db]=get_test_db
    sent=[]
    monkeypatch.setattr(main,'send_otp_email',lambda email,code,**kwargs:sent.append((email,code)))
    codes=iter(['123456','234567','345678','456789','567890'])
    monkeypatch.setattr(main,'generate_otp',lambda:next(codes))
    client=TestClient(main.app)
    yield client,factory,sent
    main.app.dependency_overrides.clear()
    engine.dispose()

def register(client,email='test@example.com'):
    response=client.post('/api/auth/register',json={'name':'Test User','email':email,'password':'test-password-123'})
    assert response.status_code==200
    return {'Authorization':'Bearer '+response.json()['access_token']}

def test_signup_verify_and_replay(ctx):
    client,factory,sent=ctx;headers=register(client)
    assert len(sent)==1
    assert client.get('/api/jobs',headers=headers).status_code==403
    result=client.post('/api/auth/verify-otp',headers=headers,json={'channel':'email','code':sent[-1][1]})
    assert result.status_code==200 and result.json()['user']['email_verified']
    assert client.get('/api/jobs',headers=headers).status_code==200
    assert client.post('/api/auth/verify-otp',headers=headers,json={'channel':'email','code':sent[-1][1]}).status_code==400

def test_wrong_expired_rate_limited_and_cross_account(ctx):
    client,factory,sent=ctx;headers=register(client)
    assert client.post('/api/auth/request-otp',headers=headers,json={'channel':'email'}).status_code==429
    code=sent[-1][1];wrong='000000' if code!='000000' else '111111'
    for _ in range(5):
        assert client.post('/api/auth/verify-otp',headers=headers,json={'channel':'email','code':wrong}).status_code==400
    assert client.post('/api/auth/verify-otp',headers=headers,json={'channel':'email','code':code}).status_code==429
    with factory() as db:
        otp=db.scalar(select(VerificationCode));otp.created_at=datetime.now(timezone.utc)-timedelta(minutes=2);db.commit()
    assert client.post('/api/auth/request-otp',headers=headers,json={'channel':'email'}).status_code==200
    with factory() as db:
        otp=db.scalar(select(VerificationCode).order_by(VerificationCode.id.desc()));otp.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    assert 'expired' in client.post('/api/auth/verify-otp',headers=headers,json={'channel':'email','code':sent[-1][1]}).json()['detail']
    assert client.post('/api/auth/verify-otp',json={'channel':'email','code':code}).status_code==401
    other=register(client,'other@example.com')
    assert client.post('/api/auth/verify-otp',headers=other,json={'channel':'email','code':code}).status_code==400

def test_email_failure_keeps_recoverable_account(ctx,monkeypatch):
    client,factory,sent=ctx
    def fail(*args): raise RuntimeError('private-provider-detail')
    monkeypatch.setattr(main,'send_otp_email',fail)
    response=client.post('/api/auth/register',json={'name':'Test','email':'test@example.com','password':'test-password-123'})
    assert response.status_code==200 and response.json()['otp_sent'] is False
    assert 'private-provider-detail' not in response.text
    headers={'Authorization':'Bearer '+response.json()['access_token']}
    assert client.get('/api/jobs',headers=headers).status_code==403

def test_company_history_dates_and_dedup(ctx):
    _,factory,_=ctx
    row={'source':'company','external_id':'fixture-google-2010','company':'Google','title':'Python Engineer','description':'Requires Python experience.','source_url':'https://example.com/archived-job','posted_at':'2010-06-01','date_basis':'source_datePosted'}
    with factory() as db:
        store_posting(db,row);db.commit();store_posting(db,row);db.commit()
        assert len(db.scalars(select(PostingSnapshot)).all())==1
        result=company_evidence(db,'Google','python')
        assert result['earliest_dated_posting'].year==2010
        assert result['evidence_count']==1
        assert company_evidence(db,'Microsoft','python')['evidence_count']==0
        row['description']='Requires Python and SQL.';store_posting(db,row);db.commit()
        assert len(db.scalars(select(PostingSnapshot)).all())==2
        row['external_id']='undated';row['posted_at']=None;store_posting(db,row);db.commit()
        assert company_evidence(db,'Google','sql')['dated_evidence_count']==1

def test_jsonld_does_not_infer_date_from_description():
    html='<script type="application/ld+json">{"@type":"JobPosting","hiringOrganization":{"name":"Google"},"title":"Engineer","description":"Python since 2010","dateModified":"2026-01-01"}</script>'
    rows=jsonld_postings(html,'https://example.com/job','Google')
    assert rows[0]['posted_at'] is None
    assert jsonld_postings(html,'https://example.com/job','Other Company')==[]


def test_company_alias_lookup_and_snapshot_examples(ctx):
    _, factory, _ = ctx
    row = {'source':'company','external_id':'alias-fixture','company':'Example Company',
           'title':'Engineer','description':'Oracle Integration Cloud required.',
           'source_url':'https://example.com/job','posted_at':'2020-01-01','date_basis':'source_datePosted'}
    with factory() as db:
        store_posting(db,row);db.commit()
        row['description'] += ' SQL preferred.'
        store_posting(db,row);db.commit()
        result = company_evidence(db,'example company','Oracle Integration Cloud')
        assert result['skill'] == 'oic'
        assert result['evidence_count'] == 1
        assert len(result['examples']) == 1
        assert company_evidence(db,'Other Company','oic')['evidence_count'] == 0


def test_unknown_job_match_is_persisted_as_unassessed(ctx):
    from app.models.entities import Resume, JobPosting
    client,factory,sent=ctx
    headers=register(client)
    client.post('/api/auth/verify-otp',headers=headers,json={'channel':'email','code':sent[-1][1]})
    with factory() as db:
        user=db.scalar(select(User))
        resume=Resume(user_id=user.id,filename='fixture.txt',raw_text='Python developer',parsed={})
        job=JobPosting(source='manual',company='Example',title='Unknown',description='Friendly team benefits',skills=[])
        db.add_all([resume,job]);db.commit()
        resume_id,job_id=resume.id,job.id
    response=client.post(f'/api/analyze/{resume_id}?target_job_id={job_id}',headers=headers)
    assert response.status_code==200
    assert response.json()['overall_score'] is None
    result=client.get('/api/analyses/'+str(response.json()['analysis_id']),headers=headers).json()['result']
    assert result['match_assessed'] is False

def test_password_reset_revokes_session_and_cannot_verify_email(ctx):
    client,factory,sent=ctx;headers=register(client)
    response=client.post('/api/auth/forgot-password',json={'email':'test@example.com'})
    assert response.status_code==200
    code=sent[-1][1]
    assert client.post('/api/auth/verify-otp',headers=headers,json={'channel':'email','code':code}).status_code==400
    response=client.post('/api/auth/reset-password',json={'email':'test@example.com','code':code,'password':'new-fixture-password'})
    assert response.status_code==200
    assert client.get('/api/auth/me',headers=headers).status_code==401
    assert client.post('/api/auth/login',json={'email':'test@example.com','password':'new-fixture-password'}).status_code==200
    assert client.post('/api/auth/reset-password',json={'email':'test@example.com','code':code,'password':'another-fixture-password'}).status_code==400

def test_docx_upload_analysis_and_history(ctx):
    from io import BytesIO
    from docx import Document
    client,_,sent=ctx;headers=register(client)
    client.post('/api/auth/verify-otp',headers=headers,json={'channel':'email','code':sent[-1][1]})
    document=Document();document.add_paragraph('Python developer with SQL and machine learning experience.')
    data=BytesIO();document.save(data)
    uploaded=client.post('/api/resumes',headers=headers,files={'file':('fixture.docx',data.getvalue(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
    assert uploaded.status_code==200
    assert 'python' in uploaded.json()['parsed']['skills']
    result=client.post('/api/analyze/'+str(uploaded.json()['id']),headers=headers)
    assert result.status_code==200
    assert result.json()['timeline_score'] is None
    assert client.get('/api/analyses',headers=headers).json()[0]['id']==result.json()['analysis_id']
