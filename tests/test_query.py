from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.api.endpoints.query import get_pipeline
from backend.core.database import get_db
from backend.core.security import create_access_token, hash_password
from backend.models.user import User


MOCK_RESULT = {
    "answer": "Voici le protocole.",
    "sources": [{"specialty": "Médecine Adulte", "protocol": "Test", "score": 0.9}],
}


@pytest.fixture()
def mock_user():
    return User(id=99, username="querier", hashed_password=hash_password("pass"), role="nurse")


@pytest.fixture()
def auth_headers(mock_user):
    token = create_access_token(str(mock_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def mock_db(client, mock_user):
    db = MagicMock()
    db.get.return_value = mock_user
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    def override():
        yield db

    client.app.dependency_overrides[get_db] = override
    yield db
    client.app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def mock_pipeline(client, mock_db):
    pipeline = MagicMock()
    pipeline.query.return_value = MOCK_RESULT
    client.app.dependency_overrides[get_pipeline] = lambda: pipeline
    yield pipeline
    client.app.dependency_overrides.pop(get_pipeline, None)


def test_query_success(client, auth_headers, mock_pipeline):
    res = client.post("/query", json={"question": "Protocole douleur?"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == MOCK_RESULT["answer"]
    assert "sources" in data
    assert "response_time_ms" in data


def test_query_with_specialty(client, auth_headers, mock_pipeline):
    res = client.post(
        "/query",
        json={"question": "Protocole?", "specialty": "Pédiatrie"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    mock_pipeline.query.assert_called_once_with("Protocole?", specialty="Pédiatrie")


def test_query_unauthenticated(client, mock_pipeline):
    res = client.post("/query", json={"question": "Test?"})
    assert res.status_code in (401, 403)


def test_query_missing_question(client, auth_headers, mock_pipeline):
    res = client.post("/query", json={}, headers=auth_headers)
    assert res.status_code == 422


def test_history_empty(client, auth_headers, mock_pipeline):
    res = client.get("/history", headers=auth_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_history_after_query(client, auth_headers, mock_pipeline, mock_db):
    from backend.models.query_log import QueryLog
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        QueryLog(
            id=1, user_id=99, question="Test?", specialty=None,
            answer="Réponse.", sources=[], response_time_ms=100.0,
            created_at=datetime.now(timezone.utc),
        )
    ]
    res = client.get("/history", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()) == 1
