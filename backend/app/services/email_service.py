import httpx
import logging
from ..config import settings

def send_otp_email(to_email: str, code: str, purpose: str = "email verification"):
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
