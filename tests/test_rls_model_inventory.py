"""Keep the PostgreSQL tenant RLS inventory aligned with ORM models."""
from app.db import REQUIRED_RLS_TABLES
from app.models import Base
import app.domain_models  # noqa: F401 - register mapped tables
import app.operations_models  # noqa: F401
import app.outreach.models  # noqa: F401
import app.telephony.models  # noqa: F401
import app.workforce_models  # noqa: F401
import app.security_models  # noqa: F401
import app.private_ops_models  # noqa: F401


def test_every_mapped_table_is_classified_in_the_rls_inventory():
    model_tables = set(Base.metadata.tables)
    # users is the shared identity directory, not tenant-owned business data.
    # Its global identity boundary and restricted API column grants are tested separately.
    global_identity_tables = {"users"}

    assert global_identity_tables <= model_tables
    assert model_tables - global_identity_tables == REQUIRED_RLS_TABLES
