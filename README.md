# MCP Server for Engineering Automation

An MCP (Model Context Protocol) server that gives an LLM structured, safe access to an engineering operations domain: **service catalog**, **incident management**, and **on-call scheduling**.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Seed the database with mock data
python scripts/seed.py

# Try the CLI client
python -m client.cli "show all open incidents"
python -m client.cli "list services tier 1"
python -m client.cli "who is on-call for platform today?"
python -m client.cli --list-tools
```

---

## Architecture

```
CLI Client  →  (stdio / MCP protocol)  →  MCP Server  →  SQLite DB
```

- **Server**: `server/main.py` — FastMCP registers 9 tools from decorated async functions
- **Client**: `client/cli.py` — deterministic keyword dispatcher maps natural language to tool calls
- **DB**: SQLite via aiosqlite, 4 tables, WAL mode

---

## Available Tools

### Read (safe, no side effects)

| Tool | Description |
|------|-------------|
| `list_services` | List services, filter by tier or team |
| `get_service` | Get details of one service by name |
| `list_incidents` | List incidents, filter by status/severity/service |
| `get_incident` | Get details of one incident by ID |
| `get_oncall` | Look up who is on-call, filter by team or date |

### Write (validated, audit-logged)

| Tool | Description |
|------|-------------|
| `create_service` | Register a new service |
| `create_incident` | Open a new incident |
| `update_incident` | Update status / assignee / description (lifecycle enforced) |
| `set_oncall` | Set on-call engineer for a team and date range |

### Incident Status Lifecycle

```
open → investigating → mitigated → resolved
```

`update_incident` enforces this — you cannot skip steps or re-open a resolved incident.

---

## CLI Examples

```bash
# Read operations
python -m client.cli "list services"
python -m client.cli "show services tier 1"
python -m client.cli "list open incidents"
python -m client.cli "show sev1 incidents"
python -m client.cli "get incident 2"
python -m client.cli "who is on-call today?"
python -m client.cli "who is on call for platform?"
python -m client.cli "who is oncall on 2026-04-07?"

# Write operations
python -m client.cli "create incident: database unreachable, sev1, service billing"
python -m client.cli "update incident 2 to investigating"
python -m client.cli "assign incident 3 to carol@acme.com"
python -m client.cli "resolve incident 1"
python -m client.cli "set oncall team data-eng newperson@acme.com 2026-04-07 2026-04-13"
```

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
# 72 passed in ~0.6s — no live server, no LLM API key required
```

### Test structure

| File | What it covers |
|------|---------------|
| `tests/test_models.py` | Pydantic schema validation (22 tests) |
| `tests/test_dispatcher.py` | Natural language → tool mapping (23 tests) |
| `tests/test_tools.py` | Tool logic + SQLite (27 tests) |

---

## Configuration

| Env variable | Default | Description |
|---|---|---|
| `DB_PATH` | `engineering.db` | Path to the SQLite database file |

---

## Project Structure

```
mcp-engineering/
├── server/
│   ├── main.py        # FastMCP server, tool registrations
│   ├── tools.py       # Tool implementations (async, no framework coupling)
│   ├── models.py      # Pydantic input/output schemas
│   └── db.py          # Schema, seed data, connection helper
├── client/
│   └── cli.py         # Minimal CLI client with NL dispatcher
├── tests/
│   ├── test_models.py
│   ├── test_dispatcher.py
│   └── test_tools.py
├── docs/
│   └── TECHNICAL_REPORT.md
├── scripts/
│   └── seed.py
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## Safety Design Summary

- **No delete/bulk-update tools** — they simply don't exist
- **All inputs validated by Pydantic** before any DB call
- **Status transitions enforced** — cannot re-open resolved incidents
- **Every write is audit-logged** to the `audit_log` table
- **Parameterized SQL only** — no string interpolation

See `docs/TECHNICAL_REPORT.md` for the full design rationale.
