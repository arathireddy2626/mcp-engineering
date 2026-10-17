"""
Pydantic models for all tool inputs and outputs.
These serve as the single source of truth for schemas — FastMCP reads them
to auto-generate JSON Schema for the MCP protocol layer.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ── Services ──────────────────────────────────────────────────────────────────

class ServiceRow(BaseModel):
    id: int
    name: str
    owner_team: str
    tier: int
    repo_url: Optional[str]
    created_at: str


class ListServicesInput(BaseModel):
    tier: Optional[int] = Field(None, ge=1, le=3, description="Filter by tier (1=critical, 3=low)")
    owner_team: Optional[str] = Field(None, description="Filter by owning team name")


class CreateServiceInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=80, description="Unique service name (slug)")
    owner_team: str = Field(..., min_length=1, max_length=80)
    tier: int = Field(..., ge=1, le=3, description="Service tier: 1=critical, 2=important, 3=low")
    repo_url: Optional[str] = Field(None, description="GitHub/GitLab URL")


# ── Incidents ─────────────────────────────────────────────────────────────────

Severity = Literal["sev1", "sev2", "sev3", "sev4"]
IncidentStatus = Literal["open", "investigating", "mitigated", "resolved"]


class IncidentRow(BaseModel):
    id: int
    title: str
    severity: str
    status: str
    service_id: Optional[int]
    service_name: Optional[str]
    assignee: Optional[str]
    description: Optional[str]
    created_at: str
    resolved_at: Optional[str]


class ListIncidentsInput(BaseModel):
    status: Optional[IncidentStatus] = Field(None, description="Filter by status")
    severity: Optional[Severity] = Field(None, description="Filter by severity")
    service_name: Optional[str] = Field(None, description="Filter by service name")


class CreateIncidentInput(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    severity: Severity
    service_name: Optional[str] = Field(None, description="Name of the affected service")
    assignee: Optional[str] = Field(None, description="Email of the assigned engineer")
    description: Optional[str] = Field(None, max_length=2000)


class UpdateIncidentInput(BaseModel):
    incident_id: int = Field(..., gt=0)
    status: Optional[IncidentStatus] = None
    assignee: Optional[str] = None
    description: Optional[str] = Field(None, max_length=2000)

    @field_validator("status", "assignee", "description", mode="before")
    @classmethod
    def at_least_one(cls, v):
        return v  # actual check in tool handler


# ── On-call ───────────────────────────────────────────────────────────────────

class OncallRow(BaseModel):
    id: int
    team: str
    engineer: str
    start_date: str
    end_date: str


class GetOncallInput(BaseModel):
    team: Optional[str] = Field(None, description="Filter by team name")
    date: Optional[str] = Field(
        None,
        description="ISO date (YYYY-MM-DD) to find who is on-call on that day",
    )

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, v):
        if v is None:
            return v
        import re
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("date must be YYYY-MM-DD format")
        return v


class SetOncallInput(BaseModel):
    team: str = Field(..., min_length=1)
    engineer: str = Field(..., min_length=3, description="Engineer email")
    start_date: str = Field(..., description="ISO date YYYY-MM-DD")
    end_date: str = Field(..., description="ISO date YYYY-MM-DD")

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date(cls, v):
        import re
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("date must be YYYY-MM-DD format")
        return v
