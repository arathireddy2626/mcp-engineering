"""
MCP Server entry point.

Uses FastMCP (from the `mcp` package) to register tools with full
JSON Schema derived from Pydantic models.

Transport: stdio (default) — the MCP client launches this script as a
subprocess and communicates over stdin/stdout.

Run directly:
    python -m server.main

Or via the helper script:
    python scripts/run_server.py
"""
import asyncio
import json
import sys

from mcp.server.fastmcp import FastMCP

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
import server.tools as tools_impl

mcp = FastMCP(
    "engineering-automation",
    instructions=(
        "You are an engineering operations assistant. "
        "You have tools to inspect services, manage incidents, and check on-call schedules. "
        "Always confirm destructive or write operations before executing them. "
        "For incident status updates, only move forward in the lifecycle: "
        "open → investigating → mitigated → resolved."
    ),
)


# ── READ TOOLS ────────────────────────────────────────────────────────────────

@mcp.tool()
async def list_services(
    tier: int | None = None,
    owner_team: str | None = None,
) -> str:
    """
    List all registered services.
    Optionally filter by tier (1=critical, 2=important, 3=low) or owner_team.
    Returns a JSON array of service objects.
    """
    inp = ListServicesInput(tier=tier, owner_team=owner_team)
    result = await tools_impl.list_services(inp)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_service(name: str) -> str:
    """
    Get details of a specific service by its unique name.
    Returns a JSON object or an error message if not found.
    """
    result = await tools_impl.get_service(name)
    if result is None:
        return json.dumps({"error": f"Service '{name}' not found"})
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    service_name: str | None = None,
) -> str:
    """
    List incidents ordered by severity (sev1 first) then creation time.
    Filter by status (open/investigating/mitigated/resolved),
    severity (sev1/sev2/sev3/sev4), or service_name.
    Returns a JSON array.
    """
    inp = ListIncidentsInput(status=status, severity=severity, service_name=service_name)
    result = await tools_impl.list_incidents(inp)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_incident(incident_id: int) -> str:
    """
    Get full details of a specific incident by its numeric ID.
    Returns a JSON object or an error message if not found.
    """
    result = await tools_impl.get_incident(incident_id)
    if result is None:
        return json.dumps({"error": f"Incident {incident_id} not found"})
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_oncall(
    team: str | None = None,
    date: str | None = None,
) -> str:
    """
    Look up on-call schedule.
    Pass a team name to see who is on-call for that team.
    Pass a date (YYYY-MM-DD) to find who is on-call on that specific day.
    Both filters can be combined.
    Returns a JSON array of on-call entries.
    """
    inp = GetOncallInput(team=team, date=date)
    result = await tools_impl.get_oncall(inp)
    return json.dumps(result, indent=2)


# ── WRITE TOOLS ───────────────────────────────────────────────────────────────

@mcp.tool()
async def create_service(
    name: str,
    owner_team: str,
    tier: int,
    repo_url: str | None = None,
) -> str:
    """
    Register a new service in the catalog.
    name: unique slug (e.g. 'payments-v2')
    owner_team: team name (e.g. 'platform')
    tier: 1=critical, 2=important, 3=low
    repo_url: optional GitHub/GitLab URL
    Returns the created service as JSON.
    """
    inp = CreateServiceInput(name=name, owner_team=owner_team, tier=tier, repo_url=repo_url)
    try:
        result = await tools_impl.create_service(inp)
        return json.dumps(result, indent=2)
    except ValueError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def create_incident(
    title: str,
    severity: str,
    service_name: str | None = None,
    assignee: str | None = None,
    description: str | None = None,
) -> str:
    """
    Open a new incident.
    title: short description (min 3 chars)
    severity: sev1 (critical) / sev2 / sev3 / sev4 (low)
    service_name: name of the affected service (optional)
    assignee: email of the engineer handling it (optional)
    description: detailed notes (optional)
    Returns the created incident as JSON.
    """
    inp = CreateIncidentInput(
        title=title,
        severity=severity,
        service_name=service_name,
        assignee=assignee,
        description=description,
    )
    try:
        result = await tools_impl.create_incident(inp)
        return json.dumps(result, indent=2)
    except ValueError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def update_incident(
    incident_id: int,
    status: str | None = None,
    assignee: str | None = None,
    description: str | None = None,
) -> str:
    """
    Update an existing incident.
    incident_id: numeric ID of the incident
    status: new status — must follow the lifecycle:
            open → investigating → mitigated → resolved
            (cannot re-open a resolved incident)
    assignee: reassign to a different engineer email
    description: update the description / add notes
    At least one of status, assignee, description must be provided.
    Returns the updated incident as JSON.
    """
    inp = UpdateIncidentInput(
        incident_id=incident_id,
        status=status,
        assignee=assignee,
        description=description,
    )
    try:
        result = await tools_impl.update_incident(inp)
        return json.dumps(result, indent=2)
    except ValueError as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def set_oncall(
    team: str,
    engineer: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Set the on-call engineer for a team during a date range.
    team: team name (e.g. 'platform')
    engineer: engineer email (e.g. 'alice@acme.com')
    start_date / end_date: ISO dates YYYY-MM-DD
    Replaces any existing entry for the same team + start_date.
    Returns the on-call entry as JSON.
    """
    inp = SetOncallInput(team=team, engineer=engineer, start_date=start_date, end_date=end_date)
    try:
        result = await tools_impl.set_oncall(inp)
        return json.dumps(result, indent=2)
    except ValueError as e:
        return json.dumps({"error": str(e)})


# ── Startup ───────────────────────────────────────────────────────────────────

async def _startup():
    await init_db()


def run():
    """Initialize DB then start the MCP server over stdio."""
    asyncio.run(_startup())
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
