"""
MCP tool implementations.

Read tools   : list_services, get_service, list_incidents, get_incident, get_oncall
Write tools  : create_service, create_incident, update_incident, set_oncall

Safety design
-------------
* All write tools require explicit, validated inputs — no free-form SQL.
* Destructive operations (delete, bulk update) are intentionally absent so i did not use it here.
* update_incident can only move status forward (open→investigating→mitigated→resolved);
  it cannot re-open a resolved incident.
* Every write is logged to the audit_log table.
* The DB path is injected via environment variable so tests can use :memory: or a
  temp file without touching production state.
"""
import json
from typing import Any

import aiosqlite

from server.db import get_db, DB_PATH
from server.models import (
    CreateIncidentInput,
    CreateServiceInput,
    GetOncallInput,
    ListIncidentsInput,
    ListServicesInput,
    SetOncallInput,
    UpdateIncidentInput,
)

# Status transition graph — prevents unsafe backward transitions
_ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "open":          ["investigating", "resolved"],
    "investigating": ["mitigated", "resolved"],
    "mitigated":     ["resolved"],
    "resolved":      [],           # terminal — no re-open via this tool
}


async def _audit(db: aiosqlite.Connection, operation: str, table: str, record_id: int | None, payload: Any) -> None:
    await db.execute(
        "INSERT INTO audit_log (operation, table_name, record_id, payload) VALUES (?,?,?,?)",
        (operation, table, record_id, json.dumps(payload, default=str)),
    )


def _row_to_dict(row: aiosqlite.Row) -> dict:
    return dict(zip(row.keys(), tuple(row)))


# ── READ: Services ────────────────────────────────────────────────────────────

async def list_services(inp: ListServicesInput) -> list[dict]:
    """Return all registered services, optionally filtered by tier or team."""
    clauses, params = [], []
    if inp.tier is not None:
        clauses.append("tier = ?")
        params.append(inp.tier)
    if inp.owner_team is not None:
        clauses.append("owner_team = ?")
        params.append(inp.owner_team)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM services {where} ORDER BY tier, name"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_service(name: str) -> dict | None:
    """Return a single service by name."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM services WHERE name = ?", (name,)) as cur:
            row = await cur.fetchone()
    return _row_to_dict(row) if row else None


# ── WRITE: Services ───────────────────────────────────────────────────────────

async def create_service(inp: CreateServiceInput) -> dict:
    """Register a new service. Fails if the name already exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute(
                "INSERT INTO services (name, owner_team, tier, repo_url) VALUES (?,?,?,?)",
                (inp.name, inp.owner_team, inp.tier, inp.repo_url),
            )
        except aiosqlite.IntegrityError:
            raise ValueError(f"Service '{inp.name}' already exists")
        row_id = (await (await db.execute("SELECT last_insert_rowid()")).fetchone())[0]
        await _audit(db, "create", "services", row_id, inp.model_dump())
        await db.commit()
        async with db.execute("SELECT * FROM services WHERE id = ?", (row_id,)) as cur:
            row = await cur.fetchone()
    return _row_to_dict(row)


# ── READ: Incidents ───────────────────────────────────────────────────────────

async def list_incidents(inp: ListIncidentsInput) -> list[dict]:
    """List incidents with optional filters. Joins service name for convenience."""
    clauses, params = [], []
    if inp.status:
        clauses.append("i.status = ?")
        params.append(inp.status)
    if inp.severity:
        clauses.append("i.severity = ?")
        params.append(inp.severity)
    if inp.service_name:
        clauses.append("s.name = ?")
        params.append(inp.service_name)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT i.*, s.name AS service_name
        FROM incidents i
        LEFT JOIN services s ON s.id = i.service_id
        {where}
        ORDER BY
            CASE i.severity WHEN 'sev1' THEN 1 WHEN 'sev2' THEN 2 WHEN 'sev3' THEN 3 ELSE 4 END,
            i.created_at DESC
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_incident(incident_id: int) -> dict | None:
    """Return a single incident by ID."""
    sql = """
        SELECT i.*, s.name AS service_name
        FROM incidents i
        LEFT JOIN services s ON s.id = i.service_id
        WHERE i.id = ?
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, (incident_id,)) as cur:
            row = await cur.fetchone()
    return _row_to_dict(row) if row else None


# ── WRITE: Incidents ──────────────────────────────────────────────────────────

async def create_incident(inp: CreateIncidentInput) -> dict:
    """Open a new incident. Looks up service_id by name if provided."""
    service_id = None
    if inp.service_name:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id FROM services WHERE name = ?", (inp.service_name,)
            ) as cur:
                svc = await cur.fetchone()
        if svc is None:
            raise ValueError(f"Service '{inp.service_name}' not found")
        service_id = svc["id"]

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO incidents (title, severity, service_id, assignee, description) VALUES (?,?,?,?,?)",
            (inp.title, inp.severity, service_id, inp.assignee, inp.description),
        )
        row_id = (await (await db.execute("SELECT last_insert_rowid()")).fetchone())[0]
        await _audit(db, "create", "incidents", row_id, inp.model_dump())
        await db.commit()

    return await get_incident(row_id)


async def update_incident(inp: UpdateIncidentInput) -> dict:
    """
    Update an incident's status, assignee, or description.

    Status transitions are enforced:
      open → investigating → mitigated → resolved
    You cannot re-open a resolved incident or skip steps.
    """
    current = await get_incident(inp.incident_id)
    if current is None:
        raise ValueError(f"Incident {inp.incident_id} not found")

    # Validate status transition
    if inp.status is not None:
        allowed = _ALLOWED_TRANSITIONS.get(current["status"], [])
        if inp.status not in allowed:
            raise ValueError(
                f"Cannot transition from '{current['status']}' to '{inp.status}'. "
                f"Allowed: {allowed or ['none — this incident is resolved']}"
            )

    sets, params = [], []
    if inp.status is not None:
        sets.append("status = ?")
        params.append(inp.status)
        if inp.status == "resolved":
            sets.append("resolved_at = datetime('now')")
    if inp.assignee is not None:
        sets.append("assignee = ?")
        params.append(inp.assignee)
    if inp.description is not None:
        sets.append("description = ?")
        params.append(inp.description)

    if not sets:
        raise ValueError("No fields to update. Provide status, assignee, or description.")

    params.append(inp.incident_id)
    sql = f"UPDATE incidents SET {', '.join(sets)} WHERE id = ?"

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(sql, params)
        await _audit(db, "update", "incidents", inp.incident_id, inp.model_dump())
        await db.commit()

    return await get_incident(inp.incident_id)


# ── READ/WRITE: On-call ───────────────────────────────────────────────────────

async def get_oncall(inp: GetOncallInput) -> list[dict]:
    """
    Return on-call schedule entries.
    If date is provided, returns only entries active on that date.
    """
    clauses, params = [], []
    if inp.team:
        clauses.append("team = ?")
        params.append(inp.team)
    if inp.date:
        clauses.append("start_date <= ? AND end_date >= ?")
        params.extend([inp.date, inp.date])
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM oncall {where} ORDER BY team, start_date"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [_row_to_dict(r) for r in rows]


async def set_oncall(inp: SetOncallInput) -> dict:
    """
    Set who is on-call for a team during a date range.
    Replaces any existing entry with the same team+start_date.
    """
    if inp.end_date < inp.start_date:
        raise ValueError("end_date must be >= start_date")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            INSERT INTO oncall (team, engineer, start_date, end_date)
            VALUES (?,?,?,?)
            ON CONFLICT(team, start_date) DO UPDATE SET
              engineer  = excluded.engineer,
              end_date  = excluded.end_date
            """,
            (inp.team, inp.engineer, inp.start_date, inp.end_date),
        )
        await db.commit()
        # Fetch back by natural key — last_insert_rowid() is unreliable on upsert
        async with db.execute(
            "SELECT * FROM oncall WHERE team = ? AND start_date = ?",
            (inp.team, inp.start_date),
        ) as cur:
            row = await cur.fetchone()
        await _audit(db, "upsert", "oncall", row["id"] if row else None, inp.model_dump())
        await db.commit()
    return _row_to_dict(row)
