"""
Database layer — SQLite via aiosqlite.
Handles schema creation and connection lifecycle.
"""
import os
import aiosqlite

DB_PATH = os.getenv("DB_PATH", "engineering.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    owner_team  TEXT    NOT NULL,
    tier        INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),
    repo_url    TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS incidents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    severity     TEXT    NOT NULL CHECK (severity IN ('sev1', 'sev2', 'sev3', 'sev4')),
    status       TEXT    NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'mitigated', 'resolved')),
    service_id   INTEGER REFERENCES services(id) ON DELETE SET NULL,
    assignee     TEXT,
    description  TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    resolved_at  TEXT
);

CREATE TABLE IF NOT EXISTS oncall (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    team        TEXT    NOT NULL,
    engineer    TEXT    NOT NULL,
    start_date  TEXT    NOT NULL,
    end_date    TEXT    NOT NULL,
    UNIQUE (team, start_date)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operation   TEXT    NOT NULL,
    table_name  TEXT    NOT NULL,
    record_id   INTEGER,
    payload     TEXT,
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

SEED = """
INSERT OR IGNORE INTO services (name, owner_team, tier, repo_url) VALUES
  ('api-gateway',   'platform',  1, 'https://github.com/acme/api-gateway'),
  ('auth-service',  'security',  1, 'https://github.com/acme/auth-service'),
  ('billing',       'payments',  2, 'https://github.com/acme/billing'),
  ('notifications', 'platform',  3, 'https://github.com/acme/notifications'),
  ('data-pipeline', 'data-eng',  2, 'https://github.com/acme/data-pipeline');

INSERT OR IGNORE INTO oncall (team, engineer, start_date, end_date) VALUES
  ('platform',  'alice@acme.com',  '2026-03-31', '2026-04-06'),
  ('security',  'bob@acme.com',    '2026-03-31', '2026-04-06'),
  ('payments',  'carol@acme.com',  '2026-03-31', '2026-04-06'),
  ('data-eng',  'dave@acme.com',   '2026-03-31', '2026-04-06');

INSERT OR IGNORE INTO incidents (title, severity, status, service_id, assignee, description) VALUES
  ('API gateway 5xx spike', 'sev1', 'investigating', 1, 'alice@acme.com',
   'P99 latency jumped to 8s, error rate 12%'),
  ('Auth token refresh bug', 'sev2', 'open', 2, NULL,
   'Some users unable to refresh tokens after password change'),
  ('Billing webhook delay', 'sev3', 'mitigated', 3, 'carol@acme.com',
   'Stripe webhooks delayed by ~5 min, retries catching up');
"""


async def get_db(path: str = DB_PATH) -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    return db


async def init_db(path: str = DB_PATH) -> None:
    """Create schema and seed data. Idempotent."""
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(SCHEMA)
        await db.executescript(SEED)
        await db.commit()
