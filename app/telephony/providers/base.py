"""Stable provider boundary; no vendor SDK is required by the OS domain layer."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CallRequest:
    call_id: str
    destination: str
    caller_id: str
    purpose: str
    callback_url: str


@dataclass(frozen=True)
class ProviderCallResult:
    provider: str
    provider_call_id: str
    accepted: bool


class TelephonyProvider(Protocol):
    def place_call(self, request: CallRequest) -> ProviderCallResult: ...


class ProviderNotConfigured(RuntimeError):
    """Raised when a live call is requested without an enabled provider."""


class UnconfiguredTelephonyProvider:
    """Safe default. It never places calls or simulates provider success."""
    name = "unconfigured"

    def place_call(self, request: CallRequest) -> ProviderCallResult:
        raise ProviderNotConfigured(
            "Telephony provider is not configured; no call was placed."
        )
