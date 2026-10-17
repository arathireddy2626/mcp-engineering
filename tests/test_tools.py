"""
Unit + integration tests for server tool logic.

Uses a temporary SQLite file so tests are fully isolated from any
production database. No live MCP server or LLM required.
"""
import os
import tempfile

import pytest
import pytest_asyncio

# Point DB_PATH to a temp file before importing anything that reads it
_TMP_DB = tempfile.mktemp(suffix=".db")
os.environ["DB_PATH"] = _TMP_DB

# Patch the module-level DB_PATH in db.py and tools.py
import server.db as db_mod
import server.tools as tools_mod

db_mod.DB_PATH = _TMP_DB
tools_mod.DB_PATH = _TMP_DB

from server.db import init_db
from server.models import (
    CreateIncidentInput,
    CreateServiceInput,
    GetOncallInput,
    ListIncidentsInput,
    ListServicesInput,
    SetOncallInput,
    UpdateIncidentInput,
)
from server.tools import (
    create_incident,
    create_service,
    get_incident,
    get_oncall,
    get_service,
    list_incidents,
    list_services,
    set_oncall,
    update_incident,
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_db():
    """Re-initialize the database before every test."""
    # Drop and recreate so tests are independent
    import aiosqlite
    async with aiosqlite.connect(_TMP_DB) as db:
        await db.executescript("""
            DROP TABLE IF EXISTS audit_log;
            DROP TABLE IF EXISTS oncall;
            DROP TABLE IF EXISTS incidents;
            DROP TABLE IF EXISTS services;
        """)
        await db.commit()
    await init_db(_TMP_DB)
    yield


# ── Services ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_services_all():
    result = await list_services(ListServicesInput())
    assert len(result) == 5  # 5 seeded services


@pytest.mark.asyncio
async def test_list_services_filter_tier():
    result = await list_services(ListServicesInput(tier=1))
    assert all(r["tier"] == 1 for r in result)
    names = {r["name"] for r in result}
    assert names == {"api-gateway", "auth-service"}


@pytest.mark.asyncio
async def test_list_services_filter_team():
    result = await list_services(ListServicesInput(owner_team="platform"))
    assert all(r["owner_team"] == "platform" for r in result)


@pytest.mark.asyncio
async def test_get_service_found():
    result = await get_service("api-gateway")
    assert result is not None
    assert result["name"] == "api-gateway"
    assert result["tier"] == 1


@pytest.mark.asyncio
async def test_get_service_not_found():
    result = await get_service("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_create_service_success():
    inp = CreateServiceInput(name="new-svc", owner_team="infra", tier=2)
    result = await create_service(inp)
    assert result["name"] == "new-svc"
    assert result["tier"] == 2
    # Verify it persisted
    fetched = await get_service("new-svc")
    assert fetched is not None


@pytest.mark.asyncio
async def test_create_service_duplicate():
    inp = CreateServiceInput(name="api-gateway", owner_team="platform", tier=1)
    with pytest.raises(ValueError, match="already exists"):
        await create_service(inp)


# ── Incidents ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_incidents_all():
    result = await list_incidents(ListIncidentsInput())
    assert len(result) == 3  # 3 seeded incidents


@pytest.mark.asyncio
async def test_list_incidents_filter_status():
    result = await list_incidents(ListIncidentsInput(status="open"))
    assert all(r["status"] == "open" for r in result)


@pytest.mark.asyncio
async def test_list_incidents_filter_severity():
    result = await list_incidents(ListIncidentsInput(severity="sev1"))
    assert all(r["severity"] == "sev1" for r in result)


@pytest.mark.asyncio
async def test_list_incidents_ordered_by_severity():
    result = await list_incidents(ListIncidentsInput())
    severities = [r["severity"] for r in result]
    order = {"sev1": 1, "sev2": 2, "sev3": 3, "sev4": 4}
    assert severities == sorted(severities, key=lambda s: order[s])


@pytest.mark.asyncio
async def test_get_incident_found():
    incidents = await list_incidents(ListIncidentsInput())
    first_id = incidents[0]["id"]
    result = await get_incident(first_id)
    assert result is not None
    assert result["id"] == first_id


@pytest.mark.asyncio
async def test_get_incident_not_found():
    result = await get_incident(99999)
    assert result is None


@pytest.mark.asyncio
async def test_create_incident_minimal():
    inp = CreateIncidentInput(title="DB connection pool exhausted", severity="sev2")
    result = await create_incident(inp)
    assert result["title"] == "DB connection pool exhausted"
    assert result["severity"] == "sev2"
    assert result["status"] == "open"


@pytest.mark.asyncio
async def test_create_incident_with_service():
    inp = CreateIncidentInput(
        title="Auth flapping",
        severity="sev1",
        service_name="auth-service",
        assignee="bob@acme.com",
    )
    result = await create_incident(inp)
    assert result["service_name"] == "auth-service"
    assert result["assignee"] == "bob@acme.com"


@pytest.mark.asyncio
async def test_create_incident_bad_service():
    inp = CreateIncidentInput(title="Test", severity="sev3", service_name="no-such-svc")
    with pytest.raises(ValueError, match="not found"):
        await create_incident(inp)


# ── Incident status transitions ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_incident_valid_transition():
    # start from open → investigating
    incidents = await list_incidents(ListIncidentsInput(status="open"))
    inc_id = incidents[0]["id"]
    result = await update_incident(UpdateIncidentInput(incident_id=inc_id, status="investigating"))
    assert result["status"] == "investigating"


@pytest.mark.asyncio
async def test_update_incident_full_lifecycle():
    inp = CreateIncidentInput(title="Lifecycle test", severity="sev4")
    inc = await create_incident(inp)
    inc_id = inc["id"]

    for step in ["investigating", "mitigated", "resolved"]:
        result = await update_incident(UpdateIncidentInput(incident_id=inc_id, status=step))
        assert result["status"] == step

    # resolved_at should be set
    assert result["resolved_at"] is not None


@pytest.mark.asyncio
async def test_update_incident_invalid_transition_resolved_reopen():
    """Cannot re-open a resolved incident."""
    inp = CreateIncidentInput(title="Resolved test", severity="sev4")
    inc = await create_incident(inp)
    inc_id = inc["id"]
    for step in ["investigating", "mitigated", "resolved"]:
        await update_incident(UpdateIncidentInput(incident_id=inc_id, status=step))

    with pytest.raises(ValueError, match="Cannot transition"):
        await update_incident(UpdateIncidentInput(incident_id=inc_id, status="open"))


@pytest.mark.asyncio
async def test_update_incident_skip_step_rejected():
    """Cannot skip from open directly to mitigated."""
    inp = CreateIncidentInput(title="Skip test", severity="sev3")
    inc = await create_incident(inp)
    with pytest.raises(ValueError, match="Cannot transition"):
        await update_incident(UpdateIncidentInput(incident_id=inc["id"], status="mitigated"))


@pytest.mark.asyncio
async def test_update_incident_no_fields():
    incidents = await list_incidents(ListIncidentsInput())
    inc_id = incidents[0]["id"]
    with pytest.raises(ValueError, match="No fields"):
        await update_incident(UpdateIncidentInput(incident_id=inc_id))


@pytest.mark.asyncio
async def test_update_incident_reassign():
    incidents = await list_incidents(ListIncidentsInput(status="open"))
    inc_id = incidents[0]["id"]
    result = await update_incident(UpdateIncidentInput(incident_id=inc_id, assignee="newperson@acme.com"))
    assert result["assignee"] == "newperson@acme.com"


@pytest.mark.asyncio
async def test_update_incident_not_found():
    with pytest.raises(ValueError, match="not found"):
        await update_incident(UpdateIncidentInput(incident_id=99999, status="resolved"))


# ── On-call ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_oncall_all():
    result = await get_oncall(GetOncallInput())
    assert len(result) == 4  # 4 seeded entries


@pytest.mark.asyncio
async def test_get_oncall_by_team():
    result = await get_oncall(GetOncallInput(team="platform"))
    assert all(r["team"] == "platform" for r in result)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_oncall_by_date():
    result = await get_oncall(GetOncallInput(date="2026-04-01"))
    assert len(result) == 4  # all 4 seeded entries span this date
    engineers = {r["engineer"] for r in result}
    assert "alice@acme.com" in engineers


@pytest.mark.asyncio
async def test_get_oncall_by_team_and_date():
    result = await get_oncall(GetOncallInput(team="platform", date="2026-04-01"))
    assert len(result) == 1
    assert result[0]["engineer"] == "alice@acme.com"


@pytest.mark.asyncio
async def test_set_oncall_new():
    result = await set_oncall(SetOncallInput(
        team="infra",
        engineer="new@acme.com",
        start_date="2026-04-07",
        end_date="2026-04-13",
    ))
    assert result["engineer"] == "new@acme.com"
    assert result["team"] == "infra"


@pytest.mark.asyncio
async def test_set_oncall_upsert():
    # Override an existing entry
    result = await set_oncall(SetOncallInput(
        team="platform",
        engineer="replacedperson@acme.com",
        start_date="2026-03-31",
        end_date="2026-04-06",
    ))
    assert result["engineer"] == "replacedperson@acme.com"
    # Only one entry for this team+start_date
    entries = await get_oncall(GetOncallInput(team="platform", date="2026-04-01"))
    assert len(entries) == 1
    assert entries[0]["engineer"] == "replacedperson@acme.com"


@pytest.mark.asyncio
async def test_set_oncall_invalid_date_range():
    with pytest.raises(ValueError, match="end_date"):
        await set_oncall(SetOncallInput(
            team="platform",
            engineer="x@acme.com",
            start_date="2026-04-10",
            end_date="2026-04-01",
        ))


# ── Audit log ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_ops_create_audit_entries():
    import aiosqlite
    await create_incident(CreateIncidentInput(title="Audit test", severity="sev4"))
    async with aiosqlite.connect(_TMP_DB) as db:
        async with db.execute("SELECT count(*) FROM audit_log") as cur:
            count = (await cur.fetchone())[0]
    assert count >= 1
