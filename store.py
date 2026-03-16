"""
store.py — Services CRUD using MySQL via SQLAlchemy.
Drop-in replacement for the old JSON-based store.py.
"""

import json
from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session

from database import SessionLocal, ServiceRow, service_to_dict


# ── Internal session helper ───────────────────────────────────────────────────

def _db() -> Session:
    return SessionLocal()


# ── Public API (same interface as old store.py) ───────────────────────────────

def load_services() -> List[dict]:
    db = _db()
    try:
        return [service_to_dict(r) for r in db.query(ServiceRow).all()]
    finally:
        db.close()


def save_services(services: List[dict]) -> None:
    """
    Bulk upsert — replaces the entire services list.
    Called by scheduler after pinging.
    """
    db = _db()
    try:
        # Build lookup of existing rows
        existing = {r.id: r for r in db.query(ServiceRow).all()}
        incoming_ids = {s["id"] for s in services}

        # Delete rows that were removed
        for row_id, row in existing.items():
            if row_id not in incoming_ids:
                db.delete(row)

        # Upsert each service
        for svc in services:
            _apply(existing.get(svc["id"]), svc, db)

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[STORE] save_services error: {e}")
        raise
    finally:
        db.close()


def save_service(svc: dict) -> None:
    """Update or insert a single service."""
    db = _db()
    try:
        existing = db.query(ServiceRow).filter(ServiceRow.id == svc["id"]).first()
        _apply(existing, svc, db)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[STORE] save_service error: {e}")
        raise
    finally:
        db.close()


# ── Internal helper ───────────────────────────────────────────────────────────

def _apply(row: ServiceRow | None, svc: dict, db: Session) -> None:
    """Apply dict values onto an existing or new ServiceRow."""
    last_pinged = None
    if svc.get("last_pinged"):
        try:
            lp = svc["last_pinged"]
            if isinstance(lp, str):
                last_pinged = datetime.fromisoformat(lp.replace("Z", "+00:00"))
            else:
                last_pinged = lp
        except Exception:
            pass

    history_json = json.dumps(svc.get("history") or [])

    if row is None:
        row = ServiceRow(
            id            = svc["id"],
            name          = svc["name"],
            url           = svc["url"],
            interval      = svc.get("interval", 10),
            enabled       = svc.get("enabled", True),
            status        = svc.get("status", "idle"),
            response_time = svc.get("response_time"),
            last_pinged   = last_pinged,
            history       = history_json,
            created_by    = svc.get("created_by"),
        )
        db.add(row)
    else:
        row.name          = svc["name"]
        row.url           = svc["url"]
        row.interval      = svc.get("interval", 10)
        row.enabled       = svc.get("enabled", True)
        row.status        = svc.get("status", row.status)
        row.response_time = svc.get("response_time", row.response_time)
        row.last_pinged   = last_pinged or row.last_pinged
        row.history       = history_json
        if svc.get("created_by"):
            row.created_by = svc["created_by"]