import os
import pytest

# Ensure SQLite is used during test collection
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_HOST"] = "localhost"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

from database import Base, get_db
from main import app

# In-memory SQLite Database for test isolation
engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    return TestClient(app)

def test_health_check(client):
    with patch("main.redis_client.ping", return_value=True), \
         patch("main.engine.connect"):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

def test_shorten_url(client):
    with patch("main.redis_client.set") as mock_redis_set:
        payload = {"url": "https://example.com/very/long/url"}
        response = client.post("/shorten", json=payload)
        
        assert response.status_code == 201
        data = response.json()
        assert "short_code" in data
        assert len(data["short_code"]) == 6
        assert data["original_url"] == "https://example.com/very/long/url"
        assert data["click_count"] == 0
        assert mock_redis_set.call_count == 2

def test_shorten_invalid_url(client):
    payload = {"url": "invalid-url-string"}
    response = client.post("/shorten", json=payload)
    assert response.status_code == 422

def test_redirect_to_url_cache_hit(client):
    with patch("main.redis_client.get", return_value="https://example.com"), \
         patch("main.redis_client.incr") as mock_incr:
        
        client.post("/shorten", json={"url": "https://example.com"})
        response = client.get("/abc123", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "https://example.com"
        mock_incr.assert_called_once_with("clicks:abc123")

def test_redirect_not_found(client):
    with patch("main.redis_client.get", return_value=None):
        response = client.get("/nonexistent", follow_redirects=False)
        assert response.status_code == 404
        assert response.json() == {"detail": "Short URL not found"}

def test_get_stats(client):
    with patch("main.redis_client.set"):
        create_res = client.post("/shorten", json={"url": "https://target-domain.com"})
        short_code = create_res.json()["short_code"]

    with patch("main.redis_client.get", return_value="5"):
        stats_res = client.get(f"/stats/{short_code}")
        assert stats_res.status_code == 200
        data = stats_res.json()
        assert data["short_code"] == short_code
        assert data["click_count"] == 5
        assert data["original_url"] == "https://target-domain.com"