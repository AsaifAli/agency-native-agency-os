"""Explicit outbox handler registry.

No production side-effect handlers are enabled by default. Register a handler
only after its authorization, idempotency, timeout, and failure behavior have
been reviewed. Unhandled event types remain pending rather than being dropped.
"""
from app.outbox_service import OutboxHandler

OUTBOX_HANDLERS: dict[str, OutboxHandler] = {}
