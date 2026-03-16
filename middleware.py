"""
middleware.py — FastAPI dependency functions for route protection.

Usage in routes:
    @app.get("/api/services")
    def get_services(current_user: dict = Depends(require_approved)):
        ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth import decode_token

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Dependency: extract and verify JWT from Authorization header.
    Returns the decoded token payload.
    Any valid (non-expired) token passes — regardless of status.
    """
    return decode_token(credentials.credentials)


def require_approved(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Dependency: user must be signed in AND have status = 'approved'.
    Fetches latest status from DB to prevent stale JWT issues.
    """
    from users import get_user_by_id
    user = get_user_by_id(current_user["sub"])
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if user.get("status") != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is pending admin approval.",
        )
    return user


def require_admin(
    current_user: dict = Depends(require_approved),
) -> dict:
    """
    Dependency: user must be approved AND have role = 'admin'.
    `require_approved` already fetched the latest user from DB.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user