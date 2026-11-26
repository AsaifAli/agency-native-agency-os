import json
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.managed_agents import ManagedAgentsRuntime
from app.integrations.runtime import (
    ExecutionRequest,
    RuntimeCancelled,
    RuntimeManualReviewRequired,
    RuntimeNotConfiguredError,
    RuntimePaused,
    RuntimeTransientError,
)
from app.models import DataClass
