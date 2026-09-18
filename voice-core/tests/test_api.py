import jwt
from fastapi.testclient import TestClient

from app.api import _safe_label, app


def test_safe_label_removes_unsafe_room_characters() -> None:
    assert _safe_label("  Jane Doe / 张三 ") == "Jane-Doe"


def test_safe_label_has_guest_fallback() -> None:
    assert _safe_label("张三") == "guest"


def test_token_creates_isolated_room_without_exposing_secret() -> None:
    response = TestClient(app).post("/token", json={"display_name": "Jane Doe"})

    assert response.status_code == 200
    body = response.json()
    claims = jwt.decode(body["token"], options={"verify_signature": False})
    assert body["room"].startswith("voice-")
    assert body["identity"].startswith("Jane-Doe-")
    assert claims["video"]["room"] == body["room"]
    assert "secret" not in body
