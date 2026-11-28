"""Immutable Agent version API contracts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentVersionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    department: str = Field(min_length=1, max_length=100)
    instructions: str = Field(default="", max_length=50000)
    runtime: Literal["claude_managed_agents", "mock"]
    data_class: Literal["synthetic", "public", "commercial", "confidential", "regulated"]
    runtime_config: dict = Field(default_factory=dict)
    change_reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_runtime_options(self):
        unknown = set(self.runtime_config) - {"timeout_seconds"}
        if unknown:
            raise ValueError("runtime_config contains unsupported keys")
        if "timeout_seconds" in self.runtime_config:
            timeout = self.runtime_config["timeout_seconds"]
            if (
                self.runtime != "claude_managed_agents"
                or isinstance(timeout, bool)
                or not isinstance(timeout, int)
                or not 30 <= timeout <= 3600
            ):
                raise ValueError("timeout_seconds must be an integer from 30 to 3600 for Managed Agents")
        return self


class AgentVersionAction(BaseModel):
    approval_id: str = Field(min_length=1, max_length=36)


class AgentVersionRollback(BaseModel):
    approval_id: str = Field(min_length=1, max_length=36)
    change_reason: str = Field(min_length=1, max_length=500)


class AgentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent_id: str
    version_number: int
    name: str
    department: str
    instructions: str
    runtime: str
    data_class: str
    runtime_config: dict
    config_sha256: str
    change_reason: str
    created_by: str | None
    created_at: datetime
    is_active: bool
