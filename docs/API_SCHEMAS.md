# Mediary 단계별 JSON 스키마

현재 FastAPI/Pydantic 구현을 기준으로 정리한 문서다. 사진은 OCR 없이 HCX-005가 직접 해석하고, 음성은 사용자가 확정한 STT transcript만 대화와 최종 일기에 사용한다.

## 1. 세션 생성

`POST /diary/sessions`

```json
{
  "request": {"user_id": "string", "diary_date": "YYYY-MM-DD"},
  "response": {
    "session_id": "uuid",
    "user_id": "string",
    "diary_date": "YYYY-MM-DD",
    "status": "collecting"
  }
}
```

## 2. 사진·음성 전처리

`POST /diary/{session_id}/inputs`

```json
{
  "request": {
    "items": [{
      "input_id": "string",
      "type": "photo | audio | text",
      "text": "string | null",
      "file_base64": "string | null",
      "mime_type": "string | null",
      "duration_seconds": 10.5,
      "captured_at": "ISO-8601 datetime | null"
    }]
  },
  "response": {
    "session_id": "uuid",
    "items": [{
      "input_id": "string",
      "type": "photo | audio | text",
      "storage_url": "string | null",
      "content_hash": "string | null",
      "size_bytes": 0,
      "mime_type": "string | null",
      "transcript": "string | null",
      "transcript_confirmed": false,
      "captured_at": "ISO-8601 datetime | null",
      "status": "ok | failed",
      "error_code": "string | null",
      "error_reason": "string | null",
      "provider_meta": {}
    }],
    "error_count": 0
  }
}
```

사진은 HCX-005에 이미지 입력으로 전달된다. 음성은 STT 결과를 반환하지만 `transcript_confirmed=true`가 되기 전에는 채팅 입력으로 사용할 수 없다.

## 3. 음성 transcript 확인·수정

`PUT /diary/{session_id}/inputs/{input_id}/transcript`

```json
{
  "request": {"transcript": "사용자가 확인하거나 수정한 내용"},
  "response": {
    "session_id": "uuid",
    "input_id": "string",
    "transcript": "사용자가 확인하거나 수정한 내용",
    "transcript_confirmed": true
  }
}
```

## 4. HCX-005 사실 추출

채팅 API 내부 1차 구조화 출력이다.

```json
{
  "events": [{
    "event": "string",
    "time": "string | null",
    "people": ["string"],
    "location": "string | null",
    "actions": ["string"],
    "emotions": [{
      "label": "string",
      "excerpt": "원문 그대로의 감정 구절",
      "input_id": "string"
    }],
    "evidence": [{"input_id": "string", "excerpt": "string | null"}]
  }],
  "coverage": {
    "has_person": true,
    "has_location": true,
    "has_emotion": true,
    "sufficient": true,
    "missing_fields": []
  },
  "image_observations": [{
    "input_id": "string",
    "description": "string",
    "observed_facts": ["string"],
    "related_event": "string | null"
  }],
  "image_clarity": [{
    "input_id": "string",
    "unclear": false,
    "reason": "string | null"
  }],
  "model": "HCX-005"
}
```

백엔드 sanitize가 감정 `excerpt/input_id`, evidence, 누락 필드와 다음 질문 대상을 검증·확정한다.

## 5. 사용자 응답 합성 및 채팅 응답

`POST /diary/{session_id}/chat`

```json
{
  "request": {"message": "string", "input_ids": ["string"]},
  "response": {
    "session_id": "uuid",
    "stage": "WorkflowStage",
    "questions_asked_count": 0,
    "turn": {
      "events": [],
      "coverage": {},
      "image_observations": [],
      "image_clarity": [],
      "model": "HCX-005",
      "response": {
        "reaction": "질문이 섞이지 않은 공감 반응",
        "question": "다음 필수 질문 | null"
      }
    },
    "review_summary": "누구와 어디에서 무엇을 했고 어떤 감정이었는지 한 줄 요약 | null"
  }
}
```

`reaction/question`은 같은 HCX-005 어댑터를 사용하는 별도 호출에서 함께 생성한다. 새 모델 서버나 별도 에이전트를 띄우는 구조는 아니다. 질문 대상은 LLM이 아니라 백엔드가 `person → location → emotion` 중 누락된 항목으로 확정한다.

## 6. 정보 확인 게이트

`POST /diary/{session_id}/review`

```json
{
  "request": {"action": "summary_yes | summary_no | more_yes | more_no | skip_current"},
  "response": {
    "session_id": "uuid",
    "stage": "WorkflowStage",
    "review_summary": "string | null",
    "turn": "다음 질문이 있으면 ChatbotTurnResult | null"
  }
}
```

주요 흐름은 `awaiting_summary_confirmation → awaiting_more_content/awaiting_correction → adding_more_content/ready_to_generate`다.
필수정보 질문 횟수에는 고정 상한이 없다. 확인될 때까지 같은 필드를 다시 물을 수 있으며,
사용자가 `skip_current`를 선택하면 그 필드는 건너뛰고 다음 미확인 필드로 이동한다.

## 7. HCX-007 일기·대본 생성

`POST /diary/{session_id}/generate`는 `202 Accepted`와 작업 ID를 반환하고, `GET /diary/jobs/{job_id}`로 결과를 조회한다.

```json
{
  "generate_response": {"job_id": "uuid", "status": "queued"},
  "job_response": {
    "job_id": "uuid",
    "status": "queued | running | completed | failed",
    "result": {
      "title": "string",
      "paragraphs": ["string"],
      "summary": "string",
      "narration_script": "string",
      "emotion_tags": ["string"],
      "evidence_input_ids": ["string"],
      "model": "HCX-007"
    },
    "error_code": "string | null"
  }
}
```

최종 생성에는 해당 세션의 전체 대화와 확정된 입력을 사용한다. 사람·장소·감정은 생성 게이트의 필수 정보이고, 그 밖에 사용자가 추가로 말한 사건과 세부 내용도 일기와 대본에 포함한다.

## 8. 캘린더 조회 (K-01/K-02)

### 8.1 월간/기간 목록 (미리보기)

`GET /api/calendar`

```json
{
  "request": {
    "user_id": "string",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "status": ["active | processing | completed | failed"],
    "emotion": "string | null",
    "keyword": "string | null",
    "latitude": 0.0,
    "longitude": 0.0,
    "radius": 1000.0
  },
  "response": {
    "user_id": "string",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "summary": {
      "total_entries": 0,
      "completed_entries": 0,
      "processing_entries": 0,
      "failed_entries": 0,
      "approved_entries": 0
    },
    "entries": [{
      "diary_date": "YYYY-MM-DD",
      "session_id": "string",
      "status": "active | processing | completed | failed",
      "db_status": "string",
      "title": "string | null",
      "summary": "string | null",
      "emotion_tags": ["string"],
      "approved": true,
      "video_status": "pending | processing | completed | failed | null",
      "location_name": "string | null"
    }]
  }
}
```

`awaiting_approval` DB 상태는 목록/집계에서 `processing`으로 정규화된다.

### 8.2 일기 상세

`GET /api/calendar/{session_id}?user_id=...`

목록 항목 + `content`, `paragraphs`, `evidence_input_ids`, `narration_*`, `diary_inputs`, `versions`.

### 8.3 감정 태그 목록

`GET /api/calendar/emotions?user_id=...&start_date=...&end_date=...`

```json
{"user_id": "string", "start_date": "YYYY-MM-DD | null", "end_date": "YYYY-MM-DD | null", "emotions": ["happy"]}
```

## 전체 단계 상태값

`collecting`, `needs_clarification`, `awaiting_summary_confirmation`, `awaiting_more_content`, `adding_more_content`, `awaiting_correction`, `ready_to_generate`, `drafted`, `approved`, `rendering`, `completed`, `failed`
