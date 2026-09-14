import base64
from email import message_from_bytes
import httpx
import pytest
from app.services import email_service as mail

def test_gmail_sends_mime_with_refreshed_token(monkeypatch):
    for key, value in {'email_provider':'gmail', 'gmail_client_id':'fixture-id',
                       'gmail_client_secret':'fixture-secret', 'gmail_refresh_token':'fixture-refresh',
                       'gmail_sender_email':'sender@example.com'}.items():
        monkeypatch.setattr(mail.settings, key, value)
    calls=[]
    def post(url, **kwargs):
        calls.append((url,kwargs))
        return httpx.Response(200,json={'access_token':'fixture-access'} if len(calls)==1 else {'id':'sent'})
    monkeypatch.setattr(mail.httpx,'post',post)
    assert mail.send_otp_email('recipient@example.com','123456') == {'id':'sent'}
    assert calls[0][1]['data']['grant_type']=='refresh_token'
    assert calls[1][1]['headers']['Authorization']=='Bearer fixture-access'
    message=message_from_bytes(base64.urlsafe_b64decode(calls[1][1]['json']['raw']))
    assert message['To']=='recipient@example.com'
    assert '123456' in message.get_payload()

def test_gmail_missing_configuration_fails_closed(monkeypatch):
    monkeypatch.setattr(mail.settings,'email_provider','gmail')
    monkeypatch.setattr(mail.settings,'gmail_refresh_token','')
    monkeypatch.setattr(mail.settings,'gmail_client_id','')
    with pytest.raises(RuntimeError,match='not configured'):
        mail.send_otp_email('recipient@example.com','123456')
