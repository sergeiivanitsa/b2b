import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("GATEWAY_SHARED_SECRET", "test-shared-secret")
os.environ.setdefault("GATEWAY_CLOCK_SKEW_SECONDS", "60")
os.environ.setdefault("GATEWAY_NONCE_TTL_SECONDS", "300")

from gateway_api import settings as settings_module

settings_module.get_settings.cache_clear()

from gateway_api.main import app


@pytest.fixture()
def client():
    return TestClient(app)
