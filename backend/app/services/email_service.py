import httpx
import logging
import base64
from email.message import EmailMessage
from ..config import settings

def send_otp_email(to_email: str, code: str, purpose: str = "email verification"):
    if settings.email_provider == 'gmail':
        return send_gmail_email(to_email, code, purpose)
    if settings.email_provider != 'resend':
        raise RuntimeError('Unsupported email provider')
    if not settings.resend_api_key:
        logging.getLogger(__name__).error('Email delivery failed: provider key not configured')
        raise RuntimeError("RESEND_API_KEY is not configured")

    response = httpx.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": settings.otp_from_email,
            "to": [to_email],
            "subject": f"Your Resume Verifier {purpose} code",
            "html": f"""
                <h2>Resume Verifier AI</h2>
                <p>Your verification code is:</p>
                <h1>{code}</h1>
                <p>This code expires in 10 minutes.</p>
            """,
        },
        timeout=15.0,
    )

    if response.is_error:
        # Log only status, never response bodies, recipients, credentials or codes.
        logging.getLogger(__name__).error('Email delivery rejected by provider: HTTP %s', response.status_code)
    response.raise_for_status()
    return response.json()

def send_gmail_email(to_email: str, code: str, purpose: str):
    if not all((settings.gmail_client_id, settings.gmail_client_secret, settings.gmail_sender_email)):
        raise RuntimeError('Gmail sending is not configured')
    from .gmail_connection import stored_token
    refresh_token = settings.gmail_refresh_token or stored_token()
    if not all((settings.gmail_client_id, settings.gmail_client_secret,
                refresh_token, settings.gmail_sender_email)):
        raise RuntimeError('Gmail sending is not configured')
    token = httpx.post('https://oauth2.googleapis.com/token', data={
        'client_id': settings.gmail_client_id,
        'client_secret': settings.gmail_client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }, timeout=15)
    if token.is_error:
        logging.getLogger(__name__).error('Gmail authorization failed: HTTP %s', token.status_code)
        raise RuntimeError('Gmail authorization failed')
    message = EmailMessage()
    message['From'] = settings.gmail_sender_email
    message['To'] = to_email
    message['Subject'] = f'Your Resume Verifier {purpose} code'
    message.set_content(f'Your {purpose} code is: {code}\nThis code expires in 10 minutes.')
    response = httpx.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
        headers={'Authorization': 'Bearer ' + token.json()['access_token']},
        json={'raw': base64.urlsafe_b64encode(message.as_bytes()).decode('ascii')}, timeout=15)
    if response.is_error:
        logging.getLogger(__name__).error('Gmail delivery rejected: HTTP %s', response.status_code)
        raise RuntimeError('Gmail delivery failed')
    return response.json()
