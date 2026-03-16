"""
auth.py — JWT creation/verification + Google OAuth token exchange.
"""

import os
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from jose import JWTError, jwt

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

JWT_SECRET         = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM      = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 days

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_TOKEN_URL     = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL  = "https://www.googleapis.com/oauth2/v3/userinfo"

APP_URL      = os.getenv("APP_URL",      "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(user: dict) -> str:
    """Create a signed JWT with user id, email, role, status."""
    expire  = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub":    user["id"],
        "email":  user["email"],
        "name":   user["name"],
        "role":   user["role"],
        "status": user["status"],
        "exp":    expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")


# ── Google OAuth ──────────────────────────────────────────────────────────────

def google_oauth_url() -> str:
    """Return the Google consent screen URL."""
    redirect_uri = f"{APP_URL}/api/auth/google/callback"
    return (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
        "&prompt=select_account"
    )


async def exchange_google_code(code: str) -> dict:
    """
    Exchange the Google authorization code for user info.
    Returns: { email, name, picture, google_id }
    """
    redirect_uri = f"{APP_URL}/api/auth/google/callback"

    async with httpx.AsyncClient() as client:
        # Step 1: exchange code for access token
        token_res = await client.post(GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        })
        if token_res.status_code != 200:
            raise HTTPException(400, f"Google token exchange failed: {token_res.text}")

        # Step 2: fetch user profile
        info_res = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_res.json()['access_token']}"},
        )
        if info_res.status_code != 200:
            raise HTTPException(400, "Failed to fetch Google user info")

        info = info_res.json()
        return {
            "email":     info.get("email", ""),
            "name":      info.get("name", ""),
            "picture":   info.get("picture", ""),
            "google_id": info.get("sub", ""),
        }