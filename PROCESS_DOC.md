# Process Documentation — MCP Server for Engineering Automation

*Take-home assignment process log — copy this into your Google Doc*

---

## 1. First Decision: Option Choice

**Chose Option 2 (MCP Server)** as the second assignment deliverable (Option 1, Text-to-Image, was completed separately).

**Why MCP was interesting:**
MCP is a relatively new protocol (Anthropic, late 2024) that standardizes how LLMs interact with external tools. The spec itself is elegant — tools are just JSON-Schema-described functions, and the server/client lifecycle is a thin wrapper over JSON-RPC 2.0 over stdio or SSE. The assignment's framing around "safety" and "tool contracts" is directly what MCP is designed to address.

---

## 2. Tooling & Editor Setup

| Tool | Choice |
|------|--------|
| Editor | Cursor (VS Code-based) |
| AI assistant | Claude via Perplexity Computer |
| Language | Python 3.12 |
| MCP SDK | `mcp[cli]` (official Anthropic Python SDK, includes FastMCP) |
| Database | SQLite via `aiosqlite` |
| Framework | FastMCP (part of the official `mcp` package) |
| Tests | pytest + pytest-asyncio |

---

## 3. Domain Decision

**Chose: Engineering Operations Tracker** — services, incidents, on-call schedule.

**Why not a GitHub wrapper or a Postgres TODO app?**
- A GitHub wrapper would require OAuth tokens in tests, making tests non-deterministic
- A plain TODO app doesn't have natural safety constraints
- Engineering operations (incident lifecycle, on-call rotation) has clear read/write semantics and natural places where you'd want to enforce safety rules (can't reopen a resolved incident, can't delete a service that has open incidents, etc.)

The SQLite approach keeps setup to zero — no Docker, no running Postgres, just a file.

---

## 4. Early Prompts to AI

**Prompt 1 — architecture:**
> "Design an MCP server in Python for engineering automation. Domain: service catalog, incidents, on-call. Use FastMCP from the official mcp package. SQLite + aiosqlite for storage. Clear read/write separation. Safety constraints on status transitions. Audit log on all writes."

*What came back:* A clean 5-file structure: `db.py`, `models.py`, `tools.py`, `main.py` (server), `cli.py` (client). FastMCP uses `@mcp.tool()` decorators with Python type hints — it generates JSON Schema automatically. No boilerplate MCP protocol code needed.

**Prompt 2 — safety design:**
> "For the update_incident tool, enforce that status can only move forward: open → investigating → mitigated → resolved. Make it impossible to re-open a resolved incident or skip steps."

*What came back:* A simple `_ALLOWED_TRANSITIONS` dict and a validation check at the start of `update_incident`. Simple, explicit, testable — exactly the right design.

**Prompt 3 — client design:**
> "Build a minimal CLI client that takes natural language and maps to MCP tool calls. Use a deterministic regex dispatcher, not an LLM — the assignment asks for testable behavior."

*What came back:* A keyword/regex dispatcher with `elif` branches for each tool. Important design choice: this keeps the client dependency-free (no OpenAI key needed) and every dispatch path is unit-testable.

---

## 5. Key Decisions Along the Way

### 5a. FastMCP vs raw mcp.Server

The `mcp` package has two APIs: a low-level `mcp.Server` (manual JSON schema, manual dispatch) and `FastMCP` (decorator-based, type hints → schema auto-generated). FastMCP is much cleaner — the spec says "favor simple, explicit designs." FastMCP is exactly that.

### 5b. SQLite + aiosqlite instead of PostgreSQL

Zero infrastructure. The `aiosqlite` connection is fully async, WAL mode enabled. The DB_PATH is injected via environment variable — tests set it to a temp file, so tests never touch any production state. This is the single most important testing decision.

### 5c. All validation in Pydantic models, not in tool handlers

The Pydantic models (`models.py`) are the contract. FastMCP reads them to generate JSON Schema. The same models validate input in tests. This means schemas, validation, and documentation are all in one place.

### 5d. No delete tools

Deliberate omission. The assignment asks: "How do you prevent unsafe or destructive actions?" The simplest answer is: don't expose them. There is no `delete_incident` or `delete_service`. If a caller tries to invoke them, the MCP protocol returns a ToolNotFoundError.

### 5e. Dispatcher ordering bug

During testing: "get incident 42" matched `list_incidents` before `get_incident` because the `list/show/get` pattern matched first. Fixed by:
- Moving `get_incident` before `list_incidents` in the elif chain
- Adding `and not re.search(r"\b\d+\b", text)` to `list_incidents`
- Adding `and re.search(r"\b\d+\b", text)` to `get_incident`

Similarly, "set oncall" matched `get_oncall` before `set_oncall`. Fixed by placing `set_oncall` before `get_oncall` in the chain.

### 5f. SQLite upsert + last_insert_rowid() bug

`last_insert_rowid()` returns 0 when an `ON CONFLICT ... DO UPDATE` hits the conflict path (it's an update, not an insert). Fixed by fetching the row back by natural key (`team + start_date`) after the upsert commit.

---

## 6. What the Tests Cover

**72 tests, 0.6s runtime, no API keys or running services needed.**

| File | What it tests |
|------|---------------|
| `test_models.py` | Pydantic validation — bad tier values, wrong date formats, title too short, etc. |
| `test_dispatcher.py` | NL → tool mapping — every instruction pattern, including edge cases and unrecognized input |
| `test_tools.py` | Full tool logic + DB — CRUD, lifecycle enforcement, audit log, upsert, FK validation |

---

## 7. Project Structure (Final)

```
mcp-engineering/
├── server/
│   ├── main.py         # FastMCP app, tool registrations, startup
│   ├── tools.py        # Async tool implementations (read + write)
│   ├── models.py       # Pydantic schemas for all inputs
│   └── db.py           # SQLite schema, seed data, connection helper
├── client/
│   └── cli.py          # CLI client: dispatcher + MCP stdio connection
├── tests/
│   ├── test_tools.py      # Tool logic + DB (72 tests total across all files)
│   ├── test_dispatcher.py # NL dispatcher unit tests
│   └── test_models.py     # Pydantic model validation tests
├── docs/
│   └── TECHNICAL_REPORT.md
├── scripts/
│   └── seed.py
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## 8. How to Run It

```bash
# 1. Install
pip install -r requirements.txt

# 2. Seed the database
python scripts/seed.py

# 3. Try the CLI
python -m client.cli "show all open incidents"
python -m client.cli "who is on-call for platform today?"
python -m client.cli "create incident: auth service down, sev1, service auth-service"
python -m client.cli "update incident 1 to investigating"

# 4. Run tests
pip install -r requirements-dev.txt
pytest tests/ -v

# 5. List available MCP tools
python -m client.cli --list-tools
```
