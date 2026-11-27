"""Pytest-wide environment isolation.

This module is loaded before test-module collection, so importing app.db from
any test cannot accidentally bind the shared application engine to a developer
or Compose PostgreSQL database. PostgreSQL integration tests opt in through
their dedicated AGENCY_OS_TEST_* URLs and create their own engines.
"""
import os

# Deliberately override DATABASE_URL for the ordinary suite. Live PostgreSQL
# tests use explicit, separately guarded AGENCY_OS_TEST_* variables.
os.environ["DATABASE_URL"] = "sqlite:///./test_agency_os.db"
