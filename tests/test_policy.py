import pytest
from fastapi import HTTPException
from app.models import DataClass
from app.policy import assert_managed_agents_eligible

def test_synthetic_is_allowed():
    assert_managed_agents_eligible(DataClass.synthetic)

def test_public_is_allowed():
    assert_managed_agents_eligible(DataClass.public)

def test_commercial_requires_authorization():
    with pytest.raises(HTTPException):
        assert_managed_agents_eligible(DataClass.commercial)
    assert_managed_agents_eligible(DataClass.commercial, client_authorized=True)

@pytest.mark.parametrize("data_class", [DataClass.confidential, DataClass.regulated])
def test_sensitive_data_blocked_from_managed_agents(data_class):
    with pytest.raises(HTTPException):
        assert_managed_agents_eligible(data_class, client_authorized=True)
