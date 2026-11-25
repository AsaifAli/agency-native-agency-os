"""Allowlisted JWT signing-key selection with a bounded rotation window."""
from __future__ import annotations

import jwt
from jwt import InvalidTokenError

from app.config import settings


def encode_jwt(claims: dict) -> str:
    return jwt.encode(
        claims,
        settings.jwt_secret,
        algorithm="HS256",
        headers={"kid": settings.jwt_key_id},
    )


def decode_jwt(token: str, **options):
    """Decode only with an explicitly configured key; never trust arbitrary kid."""
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    current = (settings.jwt_key_id, settings.jwt_secret)
    previous = (
        (settings.jwt_previous_key_id, settings.jwt_previous_secret)
        if settings.jwt_previous_secret else None
    )

    if kid is None:
        # Pre-kid tokens were signed by the key active before this deployment.
        candidates = [item for item in (previous, current) if item is not None]
    else:
        candidates = [item for item in (current, previous) if item is not None and item[0] == kid]
        if not candidates:
            raise InvalidTokenError("Unknown JWT signing key")

    last_error = None
    for _, secret in candidates:
        try:
            return jwt.decode(token, secret, algorithms=["HS256"], **options)
        except InvalidTokenError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise InvalidTokenError("No JWT signing key is configured")
