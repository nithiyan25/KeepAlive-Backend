"""
scheduler.py — Async background task that pings services on their schedule.
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import List

import aiohttp

from store import load_services, save_services, save_service

# In-memory activity log (latest 100 entries)
activity_log: List[dict] = []


# ── Logging ───────────────────────────────────────────────────────────────────

def _add_log(name: str, url: str, status: str, response_time: int, error: str = None):
    entry = {
        "id":            str(uuid.uuid4()),
        "name":          name,
        "url":           url,
        "status":        status,
        "response_time": response_time,
        "error":         error,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }
    activity_log.insert(0, entry)
    if len(activity_log) > 100:
        activity_log.pop()
    print(f"[PING] {name} → {status.upper()} ({response_time}ms)")


# ── Ping a single service ─────────────────────────────────────────────────────

async def ping_service(service: dict) -> dict:
    """
    Ping one URL. Returns updated fields: status, response_time, last_pinged, history.
    """
    start         = time.monotonic()
    status        = "down"
    error_msg     = None
    response_time = 0  # safe default — overwritten in every branch below

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                service["url"],
                headers={"User-Agent": "KeepAlive-Pinger/1.0"},
                ssl=False,
            ) as resp:
                response_time = int((time.monotonic() - start) * 1000)
                status = "up" if resp.status < 400 else "degraded"

    except asyncio.CancelledError:
        raise

    except asyncio.TimeoutError:
        response_time = int((time.monotonic() - start) * 1000)
        status    = "timeout"
        error_msg = "Request timed out"

    except Exception as e:
        response_time = int((time.monotonic() - start) * 1000)
        status    = "down"
        error_msg = str(e)

    _add_log(service["name"], service["url"], status, response_time, error_msg)

    now_iso         = datetime.now(timezone.utc).isoformat()
    history_entry   = {"time": response_time, "ok": status == "up", "ts": now_iso}
    updated_history = (service.get("history") or [])[-29:] + [history_entry]

    return {
        "status":        status,
        "response_time": response_time,
        "last_pinged":   now_iso,
        "history":       updated_history,
    }


# ── Ping all due services ─────────────────────────────────────────────────────

async def ping_all():
    services = load_services()

    for svc in services:
        if not svc.get("enabled", True):
            continue

        last_pinged      = svc.get("last_pinged")
        interval_seconds = svc.get("interval", 10) * 60

        if last_pinged:
            try:
                last_dt = datetime.fromisoformat(last_pinged.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if elapsed < interval_seconds:
                    continue
            except Exception:
                pass

        result = await ping_service(svc)
        svc.update(result)
        save_service(svc)   # save each one immediately to DB


# ── Scheduler loop ────────────────────────────────────────────────────────────

async def scheduler_loop():
    print("[SCHEDULER] Started — checking services every 60s")
    try:
        while True:
            try:
                await ping_all()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[SCHEDULER] Unexpected error: {e}")
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        print("[SCHEDULER] Shutting down cleanly...")