"""
Validation tests for Pydantic models.
Ensures that bad inputs are caught at the schema layer before hitting the DB.
"""
import pytest
from pydantic import ValidationError

from server.models import (
    CreateIncidentInput,
    CreateServiceInput,
    GetOncallInput,
    ListIncidentsInput,
    SetOncallInput,
    UpdateIncidentInput,
)


# ── CreateServiceInput ────────────────────────────────────────────────────────

def test_create_service_valid():
    inp = CreateServiceInput(name="my-svc", owner_team="platform", tier=1)
    assert inp.tier == 1


def test_create_service_bad_tier():
    with pytest.raises(ValidationError):
        CreateServiceInput(name="x", owner_team="y", tier=5)


def test_create_service_zero_tier():
    with pytest.raises(ValidationError):
        CreateServiceInput(name="x", owner_team="y", tier=0)


def test_create_service_empty_name():
    with pytest.raises(ValidationError):
        CreateServiceInput(name="", owner_team="y", tier=1)


# ── CreateIncidentInput ───────────────────────────────────────────────────────

def test_create_incident_valid():
    inp = CreateIncidentInput(title="Disk full", severity="sev2")
    assert inp.severity == "sev2"


def test_create_incident_invalid_severity():
    with pytest.raises(ValidationError):
        CreateIncidentInput(title="Test", severity="sev5")


def test_create_incident_title_too_short():
    with pytest.raises(ValidationError):
        CreateIncidentInput(title="ab", severity="sev3")


def test_create_incident_description_too_long():
    with pytest.raises(ValidationError):
        CreateIncidentInput(title="Test title", severity="sev3", description="x" * 2001)


# ── UpdateIncidentInput ───────────────────────────────────────────────────────

def test_update_incident_valid():
    inp = UpdateIncidentInput(incident_id=1, status="resolved")
    assert inp.status == "resolved"


def test_update_incident_bad_status():
    with pytest.raises(ValidationError):
        UpdateIncidentInput(incident_id=1, status="deleted")


def test_update_incident_zero_id():
    with pytest.raises(ValidationError):
        UpdateIncidentInput(incident_id=0, status="resolved")


# ── GetOncallInput ────────────────────────────────────────────────────────────

def test_get_oncall_valid_date():
    inp = GetOncallInput(date="2026-04-01")
    assert inp.date == "2026-04-01"


def test_get_oncall_bad_date_format():
    with pytest.raises(ValidationError):
        GetOncallInput(date="01-04-2026")


def test_get_oncall_bad_date_garbage():
    with pytest.raises(ValidationError):
        GetOncallInput(date="not-a-date")


# ── SetOncallInput ────────────────────────────────────────────────────────────

def test_set_oncall_valid():
    inp = SetOncallInput(
        team="platform",
        engineer="alice@acme.com",
        start_date="2026-04-07",
        end_date="2026-04-13",
    )
    assert inp.team == "platform"


def test_set_oncall_bad_start_date():
    with pytest.raises(ValidationError):
        SetOncallInput(
            team="platform",
            engineer="alice@acme.com",
            start_date="April 7",
            end_date="2026-04-13",
        )


# ── ListIncidentsInput ────────────────────────────────────────────────────────

def test_list_incidents_invalid_status():
    with pytest.raises(ValidationError):
        ListIncidentsInput(status="deleted")


def test_list_incidents_valid_all_none():
    inp = ListIncidentsInput()
    assert inp.status is None
    assert inp.severity is None
