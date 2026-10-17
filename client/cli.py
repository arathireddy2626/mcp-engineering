"""
Minimal MCP CLI client.

Accepts a natural language instruction, uses a rule-based dispatcher to
map it to the correct MCP tool call(s), executes them against the server,
and prints the result.

Design intent: intentionally simple — no LLM required to run.
The dispatcher uses keyword matching and regex so behavior is deterministic
and fully testable. A real production client would swap the dispatcher for
an LLM-backed planner (e.g. OpenAI function calling), but that would add
API key requirements and non-determinism.

Usage:
    python -m client.cli "show all open incidents"
    python -m client.cli "who is on-call for platform today?"
    python -m client.cli "create incident: auth service down, sev1"
    python -m client.cli --list-tools
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "server", "main.py")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _server_env() -> dict[str, str]:
    """Build subprocess env so server imports resolve from project root."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        PROJECT_ROOT if not existing else f"{PROJECT_ROOT}{os.pathsep}{existing}"
    )
    return env


# ── Dispatcher ────────────────────────────────────────────────────────────────

def parse_instruction(instruction: str) -> list[tuple[str, dict]]:
    """
    Map a natural language instruction to a list of (tool_name, args) tuples.
    Returns an empty list if no tool matched.

    This is a simple keyword/regex dispatcher — deterministic and testable.
    """
    text = instruction.lower().strip()
    calls: list[tuple[str, dict]] = []

    # ── list_services ─────────────────────────────────────────────────────────
    if re.search(r"\b(list|show|get)\b.*(service|services)\b", text):
        args: dict[str, Any] = {}
        m = re.search(r"tier\s*(\d)", text)
        if m:
            args["tier"] = int(m.group(1))
        m = re.search(r"team\s+['\"]?([a-z0-9_-]+)['\"]?", text)
        if m:
            args["owner_team"] = m.group(1)
        calls.append(("list_services", args))

    # ── get_service ───────────────────────────────────────────────────────────
    elif re.search(r"\bservice\b.+\bdetail|detail.+\bservice\b|about service\b", text):
        m = re.search(r"service\s+['\"]?([a-z0-9_-]+)['\"]?", text)
        if m:
            calls.append(("get_service", {"name": m.group(1)}))

    # ── list_incidents ────────────────────────────────────────────────────────
    elif (re.search(r"\b(list|show|get)\b.*(incident|incidents|inc)\b", text)
          and not re.search(r"\b\d+\b", text)):
        args = {}
        for s in ["open", "investigating", "mitigated", "resolved"]:
            if s in text:
                args["status"] = s
                break
        for sev in ["sev1", "sev2", "sev3", "sev4"]:
            if sev in text:
                args["severity"] = sev
                break
        calls.append(("list_incidents", args))

    # ── get_incident ──────────────────────────────────────────────────────────
    elif (re.search(r"\b(get|show|detail|info|about)\b.*(incident|inc)\b", text)
          and re.search(r"\b\d+\b", text)):
        m = re.search(r"\b(\d+)\b", text)
        if m:
            calls.append(("get_incident", {"incident_id": int(m.group(1))}))

    # ── create_incident ───────────────────────────────────────────────────────
    elif re.search(r"\b(create|open|file|raise|new)\b.*(incident|inc)\b", text):
        args = {}
        # Severity: sev1..sev4 or "critical/high/medium/low"
        for pat, val in [
            (r"sev1|critical", "sev1"),
            (r"sev2|high",     "sev2"),
            (r"sev3|medium",   "sev3"),
            (r"sev4|low",      "sev4"),
        ]:
            if re.search(pat, text):
                args["severity"] = val
                break
        if "severity" not in args:
            args["severity"] = "sev3"  # default

        # Title: text after "incident:" or the full instruction
        m = re.search(r"incident[:\s]+(.+?)(?:,|\s+sev[1-4]|$)", text)
        if m:
            args["title"] = m.group(1).strip()
        else:
            args["title"] = instruction[:200]

        # Service name
        m = re.search(r"service\s+['\"]?([a-z0-9_-]+)['\"]?", text)
        if m:
            args["service_name"] = m.group(1)

        calls.append(("create_incident", args))

    # ── update_incident ───────────────────────────────────────────────────────
    elif re.search(r"\b(update|resolve|escalate|assign|mitigate)\b.*(incident|inc)\b", text):
        m = re.search(r"(\d+)", text)
        if not m:
            return []
        args = {"incident_id": int(m.group(1))}
        for s in ["investigating", "mitigated", "resolved"]:
            if s in text:
                args["status"] = s
                break
        if "resolve" in text and "status" not in args:
            args["status"] = "resolved"
        if "escalat" in text and "status" not in args:
            args["status"] = "investigating"
        # Email can appear anywhere in the sentence — search broadly
        m2 = re.search(r"([a-z0-9_.+-]+@[a-z0-9.-]+)", text)
        if m2:
            args["assignee"] = m2.group(1)
        calls.append(("update_incident", args))

    # ── set_oncall (must come BEFORE get_oncall) ─────────────────────────────
    elif re.search(r"\b(set|change)\b.*(oncall|on-call|on call)\b", text):
        args = {}
        m = re.search(r"team\s+['\"]?([a-z0-9_-]+)['\"]?", text)
        if m:
            args["team"] = m.group(1)
        m2 = re.search(r"([a-z0-9_.+-]+@[a-z0-9.-]+)", text)
        if m2:
            args["engineer"] = m2.group(1)
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
        if len(dates) >= 2:
            args["start_date"], args["end_date"] = dates[0], dates[1]
        calls.append(("set_oncall", args))

    # ── get_oncall ────────────────────────────────────────────────────────────
    elif re.search(r"\b(oncall|on-call|on call|who.*on call|on.?call)\b", text):
        args = {}
        m = re.search(r"(?:for|team)\s+['\"]?([a-z0-9_-]+)['\"]?", text)
        if m:
            args["team"] = m.group(1)
        if "today" in text:
            args["date"] = date.today().isoformat()
        else:
            m2 = re.search(r"(\d{4}-\d{2}-\d{2})", text)
            if m2:
                args["date"] = m2.group(1)
        calls.append(("get_oncall", args))

    return calls


# ── MCP client ────────────────────────────────────────────────────────────────

async def run_mcp_calls(
    tool_calls: list[tuple[str, dict]],
    server_script: str = SERVER_SCRIPT,
) -> list[dict]:
    """Connect to the MCP server over stdio, run tool calls, return results."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        env=_server_env(),
    )
    results = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for tool_name, args in tool_calls:
                response = await session.call_tool(tool_name, args)
                # response.content is a list of TextContent/ImageContent etc.
                text_parts = [c.text for c in response.content if hasattr(c, "text")]
                raw = "\n".join(text_parts)
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = raw
                results.append({"tool": tool_name, "args": args, "result": parsed})
    return results


async def list_tools(server_script: str = SERVER_SCRIPT) -> list[dict]:
    """Return the tool list from the server."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        env=_server_env(),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resp = await session.list_tools()
            return [
                {"name": t.name, "description": t.description}
                for t in resp.tools
            ]


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Engineering Automation MCP CLI client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m client.cli "show all open incidents"
  python -m client.cli "list services tier 1"
  python -m client.cli "who is on-call for platform today?"
  python -m client.cli "create incident: database unreachable, sev1, service billing"
  python -m client.cli "update incident 2 to investigating"
  python -m client.cli --list-tools
        """,
    )
    parser.add_argument("instruction", nargs="?", help="Natural language instruction")
    parser.add_argument("--list-tools", action="store_true", help="List available MCP tools")
    parser.add_argument("--server", default=SERVER_SCRIPT, help="Path to server script")
    args = parser.parse_args()

    if args.list_tools:
        tools = asyncio.run(list_tools(args.server))
        print("\nAvailable tools:\n")
        for t in tools:
            print(f"  {t['name']}")
            if t["description"]:
                first_line = t["description"].strip().split("\n")[0]
                print(f"    {first_line}")
        return

    if not args.instruction:
        parser.print_help()
        sys.exit(1)

    tool_calls = parse_instruction(args.instruction)

    if not tool_calls:
        print(
            f"\n[client] Could not parse instruction into a tool call.\n"
            f"Try: 'show all open incidents', 'list services', 'who is on-call today?'\n"
            f"Run with --list-tools to see all available tools."
        )
        sys.exit(1)

    print(f"\n[client] Instruction: {args.instruction!r}")
    for tool_name, tool_args in tool_calls:
        print(f"[client] → {tool_name}({json.dumps(tool_args)})")

    results = asyncio.run(run_mcp_calls(tool_calls, args.server))

    print()
    for r in results:
        print(f"[{r['tool']}]")
        if isinstance(r["result"], (dict, list)):
            print(json.dumps(r["result"], indent=2))
        else:
            print(r["result"])
        print()


if __name__ == "__main__":
    main()
