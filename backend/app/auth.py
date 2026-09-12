import os, hmac, hashlib, base64, json, time
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from .db import get_db
from .models.entities import User

SECRET = os.getenv("AUTH_SECRET", "change-this-secret-in-production")

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return f"pbkdf2_sha256$210000${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt_s, digest_s = encoded.split("$", 3)
        salt = base64.urlsafe_b64decode(salt_s)
        expected = base64.urlsafe_b64decode(digest_s)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

def create_token(user_id: int, ttl: int = 60 * 60 * 24 * 7) -> str:
    payload = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + ttl}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return payload + "." + sig

def decode_token(token: str) -> int:
    try:
        payload, sig = token.split(".", 1)
        expected = _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected): raise ValueError()
        data = json.loads(_unb64(payload))
        if data["exp"] < time.time(): raise ValueError()
        return int(data["sub"])
    except Exception:
        raise HTTPException(401, "Invalid or expired access token")

def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required")
    uid = decode_token(authorization.split(" ", 1)[1])
    user = db.get(User, uid)
    if not user: raise HTTPException(401, "User no longer exists")
    return user
