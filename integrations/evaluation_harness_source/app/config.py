from __future__ import annotations

import os

# Generic, local-only configuration for the retained evaluation primitives.
# Production configuration must be injected by the Agency OS, not loaded from
# a second service-specific environment or credential store.
DB_PATH = os.getenv("AUDIT_DB", "data/evaluation_dev.db")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_SCHEMA = os.getenv("DB_SCHEMA", "agency_os_eval").strip() or "agency_os_eval"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deterministic").strip().lower()
GATEWAY_BASE_URL = os.getenv("GATEWAY_BASE_URL", "").rstrip("/")
GATEWAY_SESSION_TOKEN = os.getenv("GATEWAY_SESSION_TOKEN", "").strip()
GATEWAY_MODEL = os.getenv("GATEWAY_MODEL", "").strip()
GATEWAY_PROVIDER = os.getenv("GATEWAY_PROVIDER", "gateway").strip()
GATEWAY_TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT", "45"))
GATEWAY_MAX_RETRIES = int(os.getenv("GATEWAY_MAX_RETRIES", "2"))
CIRCUIT_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "3"))
CIRCUIT_RECOVERY_SECONDS = float(os.getenv("CIRCUIT_RECOVERY_SECONDS", "30"))
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "12000"))
MIN_CONFIDENCE_FOR_ACTION = float(os.getenv("MIN_CONFIDENCE_FOR_ACTION", "0.70"))
MODEL_PRICING_JSON = os.getenv("MODEL_PRICING_JSON", "{}")
HARNESS_CONFIG_VERSION = os.getenv("HARNESS_CONFIG_VERSION", "agency-os-v1")
HUB_API_KEY = os.getenv("HUB_API_KEY", "").strip()
MODEL_PROMOTION_MIN_SCORE = float(os.getenv("MODEL_PROMOTION_MIN_SCORE", "0.90"))
