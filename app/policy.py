from fastapi import HTTPException
from app.models import DataClass

def assert_managed_agents_eligible(data_class: DataClass, client_authorized: bool = False) -> None:
    # Managed Agents is not a ZDR/BAA route. This guard is deliberately conservative.
    if data_class in {DataClass.confidential, DataClass.regulated}:
        raise HTTPException(403, "This data class is not eligible for the Managed Agents runtime")
    if data_class == DataClass.commercial and not client_authorized:
        raise HTTPException(403, "Commercial data requires documented client authorization")
