"""
Tests for the CLI natural language dispatcher.
These are pure unit tests — no I/O, no MCP server, no DB.
"""
import pytest
from client.cli import parse_instruction


# ── list_services ─────────────────────────────────────────────────────────────

def test_list_services_basic():
    calls = parse_instruction("list services")
    assert len(calls) == 1
    assert calls[0][0] == "list_services"
    assert calls[0][1] == {}


def test_list_services_tier():
    calls = parse_instruction("show services tier 1")
    assert calls[0][0] == "list_services"
    assert calls[0][1]["tier"] == 1


def test_list_services_team():
    calls = parse_instruction("list services team platform")
    assert calls[0][0] == "list_services"
    assert calls[0][1]["owner_team"] == "platform"


# ── list_incidents ────────────────────────────────────────────────────────────

def test_list_incidents_basic():
    calls = parse_instruction("show all incidents")
    assert calls[0][0] == "list_incidents"


def test_list_incidents_open():
    calls = parse_instruction("list open incidents")
    assert calls[0][0] == "list_incidents"
    assert calls[0][1]["status"] == "open"


def test_list_incidents_sev1():
    calls = parse_instruction("show sev1 incidents")
    assert calls[0][0] == "list_incidents"
    assert calls[0][1]["severity"] == "sev1"


def test_list_incidents_investigating():
    calls = parse_instruction("get investigating incidents")
    assert calls[0][0] == "list_incidents"
    assert calls[0][1]["status"] == "investigating"


# ── get_incident ──────────────────────────────────────────────────────────────

def test_get_incident():
    calls = parse_instruction("get incident 42")
    assert calls[0][0] == "get_incident"
    assert calls[0][1]["incident_id"] == 42


def test_show_incident_detail():
    calls = parse_instruction("show detail of incident 7")
    assert calls[0][0] == "get_incident"
    assert calls[0][1]["incident_id"] == 7


# ── create_incident ───────────────────────────────────────────────────────────

def test_create_incident_sev1():
    calls = parse_instruction("create incident: database down, sev1")
    assert calls[0][0] == "create_incident"
    assert calls[0][1]["severity"] == "sev1"


def test_create_incident_default_severity():
    calls = parse_instruction("open incident: network flapping")
    assert calls[0][0] == "create_incident"
    assert calls[0][1]["severity"] == "sev3"  # default


def test_create_incident_critical_keyword():
    calls = parse_instruction("create incident: total outage, critical")
    assert calls[0][0] == "create_incident"
    assert calls[0][1]["severity"] == "sev1"


def test_create_incident_with_service():
    calls = parse_instruction("create incident: latency spike, sev2, service api-gateway")
    assert calls[0][0] == "create_incident"
    assert calls[0][1].get("service_name") == "api-gateway"


# ── update_incident ───────────────────────────────────────────────────────────

def test_update_incident_to_investigating():
    calls = parse_instruction("update incident 3 to investigating")
    assert calls[0][0] == "update_incident"
    assert calls[0][1]["incident_id"] == 3
    assert calls[0][1]["status"] == "investigating"


def test_resolve_incident():
    calls = parse_instruction("resolve incident 5")
    assert calls[0][0] == "update_incident"
    assert calls[0][1]["status"] == "resolved"


def test_assign_incident():
    calls = parse_instruction("assign incident 10 to bob@acme.com")
    assert calls[0][0] == "update_incident"
    assert calls[0][1]["assignee"] == "bob@acme.com"


def test_escalate_incident():
    calls = parse_instruction("escalate incident 2")
    assert calls[0][0] == "update_incident"
    assert calls[0][1]["status"] == "investigating"


# ── get_oncall ────────────────────────────────────────────────────────────────

def test_oncall_today():
    calls = parse_instruction("who is on-call today?")
    assert calls[0][0] == "get_oncall"
    assert "date" in calls[0][1]  # today's date injected


def test_oncall_for_team():
    calls = parse_instruction("who is on call for platform?")
    assert calls[0][0] == "get_oncall"
    assert calls[0][1]["team"] == "platform"


def test_oncall_specific_date():
    calls = parse_instruction("who is oncall on 2026-04-07?")
    assert calls[0][0] == "get_oncall"
    assert calls[0][1]["date"] == "2026-04-07"


# ── set_oncall ────────────────────────────────────────────────────────────────

def test_set_oncall():
    calls = parse_instruction(
        "set oncall team platform alice@acme.com 2026-04-07 2026-04-13"
    )
    assert calls[0][0] == "set_oncall"
    assert calls[0][1]["team"] == "platform"
    assert calls[0][1]["engineer"] == "alice@acme.com"
    assert calls[0][1]["start_date"] == "2026-04-07"


# ── unrecognized ──────────────────────────────────────────────────────────────

def test_unrecognized_instruction():
    calls = parse_instruction("tell me a joke")
    assert calls == []


def test_empty_instruction():
    calls = parse_instruction("")
    assert calls == []
