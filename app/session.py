"""Authenticated encryption for short-lived OIDC browser transaction state.

Starlette's built-in SessionMiddleware signs, but does not encrypt, its cookie.
Authlib stores the PKCE verifier and OIDC nonce in request.session, so this
middleware encrypts that temporary state before it leaves the server.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from http.cookies import SimpleCookie

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class EncryptedSessionMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        secret_key: str,
        session_cookie: str = "agency_os_oidc_state",
        max_age: int = 600,
        same_site: str = "lax",
        https_only: bool = False,
    ):
        super().__init__(app)
        if len(secret_key) < 32:
            raise ValueError("OIDC state encryption key must contain at least 32 characters")
        if same_site not in {"lax", "strict", "none"}:
            raise ValueError("Invalid SameSite session-cookie policy")
        self._cipher = AESGCM(hashlib.sha256(secret_key.encode("utf-8")).digest())
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.same_site = same_site
        self.https_only = https_only
        self._aad = session_cookie.encode("utf-8")

    def _decode(self, value: str | None) -> dict:
        if not value or len(value) > 8192:
            return {}
        try:
            padded = value + "=" * (-len(value) % 4)
            raw = base64.urlsafe_b64decode(padded.encode("ascii"))
            nonce, ciphertext = raw[:12], raw[12:]
            if len(nonce) != 12 or not ciphertext:
                return {}
            decoded = self._cipher.decrypt(nonce, ciphertext, self._aad)
            data = json.loads(decoded)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _encode(self, data: dict) -> str:
        nonce = os.urandom(12)
        plaintext = json.dumps(data, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        encrypted = self._cipher.encrypt(nonce, plaintext, self._aad)
        return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii").rstrip("=")

    async def dispatch(self, request: Request, call_next):
        cookie = request.cookies.get(self.session_cookie)
        session = self._decode(cookie)
        request.scope["session"] = session
        response: Response = await call_next(request)
        if session:
            value = self._encode(session)
            response.set_cookie(
                self.session_cookie,
                value,
                max_age=self.max_age,
                httponly=True,
                secure=self.https_only,
                samesite=self.same_site,
                path="/",
            )
        elif cookie:
            response.delete_cookie(
                self.session_cookie,
                path="/",
                secure=self.https_only,
                httponly=True,
                samesite=self.same_site,
            )
        return response
