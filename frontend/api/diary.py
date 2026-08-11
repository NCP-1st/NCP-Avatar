from datetime import date
import base64
import os

import httpx


BASE_URL = os.getenv("MEDIARY_API_BASE_URL", "http://127.0.0.1:8000")


def _request(method: str, path: str, **kwargs) -> dict:
    try:
        response = httpx.request(method, BASE_URL + path, timeout=40.0, **kwargs)
    except httpx.ConnectError as exc:
        raise RuntimeError(
            "백엔드 서버에 연결할 수 없습니다. "
            + BASE_URL
            + " 서버가 실행 중인지 확인해 주세요."
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError("백엔드 응답 시간이 초과됐습니다.") from exc
    if response.is_error:
        detail = response.json().get("detail", response.text)
        if isinstance(detail, dict):
            message = detail.get("message", "요청 처리 실패")
            error_code = detail.get("error_code")
            raise RuntimeError(f"{message} ({error_code})" if error_code else message)
        raise RuntimeError(str(detail))
    return response.json()


def create_session(user_id: str, diary_date: date) -> dict:
    return _request(
        "POST",
        "/diary/sessions",
        json={"user_id": user_id, "diary_date": diary_date.isoformat()},
    )


def upload_files(session_id: str, files: list) -> dict:
    items = []
    for index, uploaded in enumerate(files, start=1):
        mime_type = uploaded.type or "application/octet-stream"
        input_type = "photo" if mime_type.startswith("image/") else "audio"
        items.append({
            "input_id": f"upload-{index}-{uploaded.name}",
            "type": input_type,
            "file_base64": base64.b64encode(uploaded.getvalue()).decode("ascii"),
            "mime_type": mime_type,
        })
    return _request("POST", f"/diary/{session_id}/inputs", json={"items": items})


def send_message(session_id: str, message: str, input_ids: list[str] | None = None) -> dict:
    return _request(
        "POST",
        f"/diary/{session_id}/chat",
        json={"message": message, "input_ids": input_ids or []},
    )


def confirm_transcript(session_id: str, input_id: str, transcript: str) -> dict:
    return _request(
        "PUT",
        f"/diary/{session_id}/inputs/{input_id}/transcript",
        json={"transcript": transcript},
    )


def review_information(session_id: str, action: str) -> dict:
    return _request(
        "POST",
        f"/diary/{session_id}/review",
        json={"action": action},
    )


def request_generation(session_id: str) -> dict:
    return _request("POST", f"/diary/{session_id}/generate")


def start_new_version_chat(session_id: str) -> dict:
    return _request("POST", f"/diary/{session_id}/versions/new-chat")


def list_versions(session_id: str) -> dict:
    return _request("GET", f"/diary/{session_id}/versions")


def approve_version(session_id: str, version_id: str) -> dict:
    return _request(
        "POST", f"/diary/{session_id}/versions/{version_id}/approve"
    )


def get_job(job_id: str) -> dict:
    return _request("GET", f"/diary/jobs/{job_id}")
