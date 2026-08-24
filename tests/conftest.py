import os
os.environ["DATABASE_URL"] = "sqlite:///./test_billing.db"
os.environ["WEBHOOK_SECRET"] = "test-secret"
from app.db import Base, engine
from app.main import app
from fastapi.testclient import TestClient
import pytest

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
