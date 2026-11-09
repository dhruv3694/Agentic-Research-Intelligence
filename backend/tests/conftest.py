import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("LOG_LEVEL", "INFO")

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
