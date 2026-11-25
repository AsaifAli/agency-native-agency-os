"""Versioned, code-owned allowlist of executable OS tools."""
from dataclasses import dataclass
import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain_models import LeadResearchDraft


class HealthReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthReadOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service: str
    database: str


class LeadResearchCaptureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_name: str = Field(min_length=2, max_length=200)
    summary: str = Field(min_length=20, max_length=3000)
    source_references: list[str] = Field(min_length=1, max_length=10)
    fit_score: int = Field(ge=0, le=100)
    confidence_score: int = Field(ge=0, le=100)
    buying_signals: list[str] = Field(default_factory=list, max_length=10)
    risks: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("company_name", "summary")
    @classmethod
    def trim_required_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("source_references")
    @classmethod
    def validate_public_https_sources(cls, values):
        for value in values:
            parsed = urlsplit(value)
            host = (parsed.hostname or "").lower().rstrip(".")
            if parsed.scheme != "https" or not host or parsed.username or parsed.password:
                raise ValueError("Source references must be public HTTPS URLs without embedded credentials")
            try:
                parsed.port
            except ValueError as exc:
                raise ValueError("Source reference has an invalid port") from exc
            if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal", ".test")):
                raise ValueError("Private or local source hosts are not allowed")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None and (
                address.is_private or address.is_loopback or address.is_link_local
                or address.is_multicast or address.is_reserved or address.is_unspecified
            ):
                raise ValueError("Private or reserved IP source hosts are not allowed")
            if len(value) > 1000:
                raise ValueError("Source reference is too long")
        if len(set(values)) != len(values):
            raise ValueError("Duplicate source references are not allowed")
        return values

    @field_validator("buying_signals", "risks")
    @classmethod
    def validate_evidence_lists(cls, values):
        if any(not isinstance(value, str) or not value.strip() or len(value) > 500 for value in values):
            raise ValueError("Evidence items must be non-empty strings up to 500 characters")
        return [value.strip() for value in values]


class LeadResearchCaptureOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_id: str
    status: Literal["pending_review"]


@dataclass(frozen=True)
class ToolSpec:
    key: str
    provider_name: str
    version: str
    description: str
    risk_level: str
    allowed_data_classes: tuple[str, ...]
    requires_approval: bool
    input_model: type[BaseModel]
    output_model: type[BaseModel]


TOOLS = {
    "system.health.read": ToolSpec(
        key="system.health.read",
        provider_name="os_system_health_read",
        version="1.0.0",
        description="Read the Agency OS API database health without accessing client records.",
        risk_level="read_only",
        allowed_data_classes=("synthetic", "public"),
        requires_approval=False,
        input_model=HealthReadInput,
        output_model=HealthReadOutput,
    ),
    "revenue.lead.research.capture": ToolSpec(
        key="revenue.lead.research.capture",
        provider_name="os_revenue_lead_research_capture",
        version="1.0.0",
        description="Save source-backed public company research as a founder-review draft; does not create a CRM lead or contact.",
        risk_level="write_draft",
        allowed_data_classes=("public",),
        requires_approval=False,
        input_model=LeadResearchCaptureInput,
        output_model=LeadResearchCaptureOutput,
    ),
}


def get_tool(tool_key: str) -> ToolSpec | None:
    return TOOLS.get(tool_key)


def list_tools() -> list[ToolSpec]:
    return list(TOOLS.values())


def validate_tool_input(spec: ToolSpec, payload: dict) -> dict:
    return spec.input_model.model_validate(payload).model_dump()


def validate_tool_output(spec: ToolSpec, payload: dict) -> dict:
    return spec.output_model.model_validate(payload).model_dump()


def execute_tool(
    db: Session,
    spec: ToolSpec,
    payload: dict,
    *,
    identity,
    idempotency_key: str,
) -> dict:
    """Execute only a registered in-process adapter; never dispatch arbitrary URLs."""
    if spec.key == "system.health.read":
        db.execute(text("SELECT 1"))
        return {"service": "agency-os-api", "database": "ok"}
    if spec.key == "revenue.lead.research.capture":
        draft = LeadResearchDraft(
            org_id=identity.org_id,
            workspace_id=identity.workspace_id,
            machine_identity_id=identity.id,
            idempotency_key=idempotency_key,
            company_name=payload["company_name"],
            summary=payload["summary"],
            source_references=payload["source_references"],
            fit_score=payload["fit_score"],
            confidence_score=payload["confidence_score"],
            buying_signals=payload["buying_signals"],
            risks=payload["risks"],
            status="pending_review",
        )
        db.add(draft)
        db.flush()
        return {"draft_id": draft.id, "status": "pending_review"}
    raise LookupError("Tool adapter is not registered")



def get_tool_by_provider_name(provider_name: str) -> ToolSpec | None:
    return next((spec for spec in TOOLS.values() if spec.provider_name == provider_name), None)


def managed_agent_custom_tool_definitions() -> list[dict]:
    """Exact Anthropic custom-tool definitions accepted by the Managed Agents adapter."""
    return [
        {
            "type": "custom",
            "name": spec.provider_name,
            "description": spec.description,
            "input_schema": spec.input_model.model_json_schema(),
        }
        for spec in TOOLS.values()
    ]
