"""Shared fixtures for sts2-commander tests."""
import sys, os

# Ensure overlay package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from overlay.card_db import CardDB


@pytest.fixture(scope="session")
def card_db():
    """CardDB instance using real project data files."""
    return CardDB()
