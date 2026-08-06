import base64

from fastapi.testclient import TestClient

from backend.dependencies import repository
from backend.main import app

client = TestClient(app)


def setup_function() -> None:
    repository.clear()


def create_session() -> str:
    response = client.post("/diary/sessions", json={"user_id": "test-user", "diary_date": "2026-08-06"})
    assert response.status_code == 201
    return response.json()["session_id"]


def test_health_and_multimodal_preprocessing() -> None:
    assert client.get("/health").json() == {"status": "ok", "adapters": "dummy"}
    session_id = create_session()
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nplaceholder").decode()
    audio = base64.b64encode(b"dummy-audio").decode()
    response = client.post(f"/diary/{session_id}/inputs", json={"items": [
        {"input_id": "text-1", "type": "text", "text": "친구와 공원에서 산책했다."},
        {"input_id": "photo-1", "type": "photo", "file_base64": image, "mime_type": "image/png"},
        {"input_id": "audio-1", "type": "audio", "file_base64": audio, "mime_type": "audio/wav"},
    ]})
    assert response.status_code == 200
    assert response.json()["error_count"] == 0
    assert all(item["status"] == "ok" for item in response.json()["items"])


def test_failed_item_can_be_retried_individually() -> None:
    session_id = create_session()
    invalid = base64.b64encode(b"not-an-image").decode()
    failed = client.post(f"/diary/{session_id}/inputs", json={"items": [
        {"input_id": "text-ok", "type": "text", "text": "정상 텍스트"},
        {"input_id": "photo-retry", "type": "photo", "file_base64": invalid},
    ]})
    body = failed.json()
    assert body["error_count"] == 1
    assert [item["status"] for item in body["items"]] == ["ok", "failed"]
    assert body["items"][1]["error_reason"]

    media = base64.b64encode(b"\x89PNG\r\n\x1a\nvalid-image-placeholder").decode()
    retried = client.post(f"/diary/{session_id}/inputs", json={"items": [{
        "input_id": "photo-retry", "type": "photo", "file_base64": media, "mime_type": "image/png"
    }]})
    assert retried.json()["items"][0]["status"] == "ok"
    assert len(repository.inputs[session_id]) == 2


def test_openapi_exposes_only_current_scope() -> None:
    paths = set(client.get("/openapi.json").json()["paths"])
    assert paths == {"/health", "/diary/sessions", "/diary/{session_id}/inputs"}
