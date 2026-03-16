from pydantic import BaseModel
from typing import Optional, List


# ── Service models ─────────────────────────────────────────────────────────────

class HistoryEntry(BaseModel):
    time: int
    ok:   bool
    ts:   str


class Service(BaseModel):
    id:            str
    name:          str
    url:           str
    interval:      int = 10
    enabled:       bool = True
    status:        str = "idle"
    response_time: Optional[int] = None
    last_pinged:   Optional[str] = None
    history:       List[HistoryEntry] = []
    created_by:    Optional[str] = None


class ServiceCreate(BaseModel):
    name:     Optional[str] = ""
    url:      str
    interval: Optional[int] = 10


class ServiceUpdate(BaseModel):
    name:     Optional[str] = None
    url:      Optional[str] = None
    interval: Optional[int] = None
    enabled:  Optional[bool] = None


# ── User models ────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id:          str
    email:       str
    name:        str
    picture:     Optional[str] = None
    role:        str           # "admin" | "user"
    status:      str           # "pending" | "approved" | "rejected"
    created_at:  str
    approved_at: Optional[str] = None


# ── Auth models ────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserOut