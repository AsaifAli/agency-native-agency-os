"""Versioned, code-owned allowlist of executable OS tools."""
from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session


class HealthReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolSpec:
    key: str
    version: str
    description: str
    risk_level: str
    allowed_data_classes: tuple[str, ...]
    requires_approval: bool
    input_model: type[BaseModel]


TOOLS = {
    "system.health.read": ToolSpec(
        key="system.health.read",
        version="1.0.0",
        description="Read the Agency OS API database health without accessing client records.",
        risk_level="read_only",
        allowed_data_classes=("synthetic", "public"),
        requires_approval=False,
        input_model=HealthReadInput,
    ),
}


def get_tool(tool_key: str) -> ToolSpec | None:
    return TOOLS.get(tool_key)


def list_tools() -> list[ToolSpec]:
    return list(TOOLS.values())


def validate_tool_input(spec: ToolSpec, payload: dict) -> dict:
    return spec.input_model.model_validate(payload).model_dump()


def execute_tool(db: Session, spec: ToolSpec, payload: dict) -> dict:
    """Execute only a registered in-process adapter; never dispatch arbitrary URLs."""
    if spec.key == "system.health.read":
        db.execute(text("SELECT 1"))
        return {"service": "agency-os-api", "database": "ok"}
    raise LookupError("Tool adapter is not registered")
