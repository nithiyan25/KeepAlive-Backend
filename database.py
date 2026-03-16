"""
database.py — MySQL connection + auto-create database and tables.

Supports both:
  - Local MySQL  (DB_SSL=false, auto-creates database)
  - Aiven MySQL  (DB_SSL=true,  database already exists — skip CREATE DATABASE)
"""

import os
import json
import ssl
from datetime import datetime, timezone

import pymysql
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, String, Integer, Boolean,
    DateTime, Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "3306"))
DB_USER     = os.getenv("DB_USER",     "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME     = os.getenv("DB_NAME",     "keepalive")

# DB_SSL=true  → Aiven (cloud) — uses SSL, skips CREATE DATABASE
# DB_SSL=false → local MySQL   — no SSL, auto-creates database
DB_SSL = os.getenv("DB_SSL", "false").lower() == "true"


# ── Step 1: Auto-create database (local only) ─────────────────────────────────

def ensure_database_exists():
    """
    Only runs for local MySQL (DB_SSL=false).
    Aiven databases are pre-created in the dashboard.
    """
    if DB_SSL:
        print(f"[DB] Aiven mode — skipping CREATE DATABASE (using `{DB_NAME}`)")
        return

    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            charset="utf8mb4",
        )
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        conn.close()
        print(f"[DB] Database `{DB_NAME}` ready.")
    except Exception as e:
        print(f"[DB] ERROR creating database: {e}")
        raise


# ── Step 2: Build SQLAlchemy connection URL ───────────────────────────────────

def get_database_url() -> str:
    base = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        f"?charset=utf8mb4"
    )
    if DB_SSL:
        # Aiven requires SSL — ssl=true tells PyMySQL to use SSL
        base += "&ssl=true"
    return base


def get_engine_kwargs() -> dict:
    kwargs = {
        "pool_pre_ping": True,   # reconnect if connection dropped
        "pool_recycle":  1800,   # recycle every 30 min (Aiven closes idle connections)
        "pool_size":     5,
        "max_overflow":  10,
        "echo":          False,
    }
    if DB_SSL:
        # Pass SSL context directly for Aiven
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode    = ssl.CERT_NONE  # Aiven uses self-signed certs
        kwargs["connect_args"] = {"ssl": ssl_ctx}
    return kwargs


# ── Step 3: Initialize engine ─────────────────────────────────────────────────

ensure_database_exists()

engine       = create_engine(get_database_url(), **get_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base         = declarative_base()


# ── Step 4: ORM models ────────────────────────────────────────────────────────

class UserRow(Base):
    __tablename__ = "users"

    id          = Column(String(36),  primary_key=True)
    email       = Column(String(255), unique=True, nullable=False, index=True)
    name        = Column(String(255), nullable=False)
    picture     = Column(Text,        nullable=True)
    role        = Column(String(20),  nullable=False, default="user")
    status      = Column(String(20),  nullable=False, default="pending")
    created_at  = Column(DateTime(timezone=True), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)


class ServiceRow(Base):
    __tablename__ = "services"

    id            = Column(String(36),  primary_key=True)
    name          = Column(String(255), nullable=False)
    url           = Column(Text,        nullable=False)
    interval      = Column(Integer,     nullable=False, default=10)
    enabled       = Column(Boolean,     nullable=False, default=True)
    status        = Column(String(20),  nullable=False, default="idle")
    response_time = Column(Integer,     nullable=True)
    last_pinged   = Column(DateTime(timezone=True), nullable=True)
    history       = Column(Text,        nullable=False, default="[]")
    created_by    = Column(String(36),  nullable=True)


# ── Step 5: Create tables ─────────────────────────────────────────────────────

def init_db():
    """Called once on startup — creates all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print("[DB] Tables ready: users, services")


# ── Dependency: get a DB session ──────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Serialization helpers ─────────────────────────────────────────────────────

def user_to_dict(row: UserRow) -> dict:
    return {
        "id":          row.id,
        "email":       row.email,
        "name":        row.name,
        "picture":     row.picture,
        "role":        row.role,
        "status":      row.status,
        "created_at":  row.created_at.isoformat()  if row.created_at  else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
    }


def service_to_dict(row: ServiceRow) -> dict:
    try:
        history = json.loads(row.history or "[]")
    except Exception:
        history = []
    return {
        "id":            row.id,
        "name":          row.name,
        "url":           row.url,
        "interval":      row.interval,
        "enabled":       bool(row.enabled),
        "status":        row.status,
        "response_time": row.response_time,
        "last_pinged":   row.last_pinged.isoformat() if row.last_pinged else None,
        "history":       history,
        "created_by":    row.created_by,
    }