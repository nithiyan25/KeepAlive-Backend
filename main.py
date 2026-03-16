import asyncio
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from auth import create_access_token, exchange_google_code, google_oauth_url
from middleware import get_current_user, require_approved, require_admin
from email_service import send_new_signup_notification, send_approval_email, send_rejection_email
from database import init_db
from models import ServiceCreate, ServiceUpdate
from scheduler import activity_log, ping_service, scheduler_loop
from store import load_services, save_services
from users import (
    create_user, get_all_users, get_user_by_email,
    get_user_by_id, get_pending_users, update_user_status, delete_user,
)

load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
ADMIN_EMAIL  = os.getenv("ADMIN_EMAIL", "")


# ── Helper: get user id from JWT payload or user dict ────────────────────────

def _user_id(current_user: dict) -> str:
    """JWT payload uses 'sub', user dict from DB uses 'id'. Handle both."""
    return current_user.get("sub") or current_user.get("id", "")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()        # 1. create tables FIRST
    _register_self() # 2. register/update self-ping service
    task = asyncio.create_task(scheduler_loop())  # 3. start scheduler
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    print("[APP] Shutdown complete.")


def _get_base_url() -> str:
    """
    Returns the correct base URL for self-ping:
    - On Render: RENDER_EXTERNAL_URL is auto-set → https://your-app.onrender.com
    - Locally:   falls back to 127.0.0.1 (avoids Windows IPv6 delay)
    """
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    return render_url if render_url else "http://127.0.0.1:8000"


def _register_self():
    """
    Register this app as a self-ping service.
    Runs on EVERY startup and updates the URL if it has changed
    (e.g. moved from local → Render, or Render URL changed).
    """
    base_url     = _get_base_url()
    health_url   = f"{base_url}/health"
    services     = load_services()
    self_service = next((s for s in services if s.get("name") == "Self (KeepAlive)"), None)

    if self_service:
        # Already exists — update URL in case environment changed
        if self_service.get("url") != health_url:
            self_service["url"] = health_url
            save_services(services)
            print(f"[SELF] Updated self-ping URL → {health_url}")
        else:
            print(f"[SELF] Self-ping OK → {health_url}")
        return

    # First run — create the entry
    services.append({
        "id":            "self-" + str(uuid.uuid4())[:8],
        "name":          "Self (KeepAlive)",
        "url":           health_url,
        "interval":      10,
        "enabled":       True,
        "status":        "idle",
        "response_time": None,
        "last_pinged":   None,
        "history":       [],
        "created_by":    "system",
    })
    save_services(services)
    print(f"[SELF] Registered self-ping → {health_url}")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="KeepAlive Pinger API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Lightweight health check — no DB queries, no processing."""
    return {"status": "ok"}


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.get("/api/auth/google")
def google_login():
    return RedirectResponse(google_oauth_url())


@app.get("/api/auth/google/callback")
async def google_callback(code: str = Query(...)):
    try:
        google_user = await exchange_google_code(code)
    except HTTPException:
        return RedirectResponse(f"{FRONTEND_URL}/login?error=google_failed")

    email = google_user["email"]
    user  = get_user_by_email(email)

    if not user:
        user = create_user(
            email=email,
            name=google_user["name"],
            picture=google_user["picture"],
            admin_email=ADMIN_EMAIL,
        )
        if user["status"] == "pending":
            send_new_signup_notification(user)

    token = create_access_token(user)
    return RedirectResponse(
        f"{FRONTEND_URL}/auth/callback?token={token}&status={user['status']}"
    )


@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(_user_id(current_user))
    if not user:
        raise HTTPException(404, "User not found")
    return user


@app.post("/api/auth/logout")
def logout():
    return {"ok": True}


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/api/admin/users")
def list_users(_: dict = Depends(require_admin)):
    return get_all_users()


@app.get("/api/admin/users/pending")
def list_pending(_: dict = Depends(require_admin)):
    return get_pending_users()


@app.post("/api/admin/users/{user_id}/approve")
def approve_user(user_id: str, _: dict = Depends(require_admin)):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user["status"] == "approved":
        raise HTTPException(400, "User is already approved")
    updated = update_user_status(user_id, "approved")
    send_approval_email(updated)
    return {"ok": True, "user": updated}


@app.post("/api/admin/users/{user_id}/reject")
def reject_user(user_id: str, _: dict = Depends(require_admin)):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    updated = update_user_status(user_id, "rejected")
    send_rejection_email(updated)
    return {"ok": True, "user": updated}


@app.delete("/api/admin/users/{user_id}")
def delete_user_route(user_id: str, _: dict = Depends(require_admin)):
    if not delete_user(user_id):
        raise HTTPException(404, "User not found")
    return {"ok": True}


@app.get("/api/admin/stats")
def admin_stats(_: dict = Depends(require_admin)):
    all_users = get_all_users()
    return {
        "total":    len(all_users),
        "pending":  sum(1 for u in all_users if u["status"] == "pending"),
        "approved": sum(1 for u in all_users if u["status"] == "approved"),
        "rejected": sum(1 for u in all_users if u["status"] == "rejected"),
        "services": len(load_services()),
    }


# ── Services ──────────────────────────────────────────────────────────────────

@app.get("/api/services")
def get_services(_: dict = Depends(require_approved)):
    return load_services()


@app.post("/api/services", status_code=201)
async def create_service(body: ServiceCreate, current_user: dict = Depends(require_approved)):
    new_svc = {
        "id":            str(uuid.uuid4())[:12],
        "name":          body.name.strip() if body.name else body.url,
        "url":           body.url.strip(),
        "interval":      body.interval or 10,
        "enabled":       True,
        "status":        "idle",
        "response_time": None,
        "last_pinged":   None,
        "history":       [],
        "created_by":    _user_id(current_user),
    }
    services = load_services()
    services.append(new_svc)
    save_services(services)
    asyncio.create_task(_ping_and_save(new_svc["id"]))
    return new_svc


@app.put("/api/services/{service_id}")
def update_service(
    service_id: str,
    body: ServiceUpdate,
    _: dict = Depends(require_approved),
):
    services = load_services()
    svc      = next((s for s in services if s["id"] == service_id), None)
    if not svc:
        raise HTTPException(404, "Service not found")
    svc.update(body.model_dump(exclude_none=True))
    save_services(services)
    return svc


@app.delete("/api/services/{service_id}")
def delete_service(service_id: str, _: dict = Depends(require_approved)):
    save_services([s for s in load_services() if s["id"] != service_id])
    return {"ok": True}


@app.post("/api/services/{service_id}/ping")
async def manual_ping(service_id: str, _: dict = Depends(require_approved)):
    services = load_services()
    svc      = next((s for s in services if s["id"] == service_id), None)
    if not svc:
        raise HTTPException(404, "Service not found")
    result = await ping_service(svc)
    svc.update(result)
    save_services(services)
    return svc


@app.get("/api/log")
def get_log(_: dict = Depends(require_approved)):
    return activity_log


# ── Helper ────────────────────────────────────────────────────────────────────

async def _ping_and_save(service_id: str):
    """Fire-and-forget: ping a newly added service after a short delay."""
    await asyncio.sleep(1)
    services = load_services()
    svc      = next((s for s in services if s["id"] == service_id), None)
    if not svc:
        return
    result = await ping_service(svc)
    svc.update(result)
    save_services(services)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)