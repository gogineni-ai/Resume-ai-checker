import httpx
from ..config import settings

def send_otp_email(to_email: str, code: str):
    if not settings.resend_api_key:
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
            "subject": "Your Resume Verifier verification code",
            "html": f"""
                <h2>Resume Verifier AI</h2>
                <p>Your verification code is:</p>
                <h1>{code}</h1>
                <p>This code expires in 10 minutes.</p>
            """,
        },
        timeout=15.0,
    )

    response.raise_for_status()
    return response.json()
