# Mediary 개발 가이드라인 (AI 코딩 에이전트용)

> Claude Code / Codex 등 AI 코딩 도구 공용 가이드. 제품 요구사항 전체는 [README.md](./README.md)와 `PRD_Mediary_MVP_Detailed_v1.0.docx` 참고.
> Codex를 사용하는 경우 이 파일을 `AGENTS.md`로 복사(또는 링크)해서 사용한다.

## 프로젝트 요약

**Mediary** — 사진·음성·텍스트를 채팅으로 업로드하면 AI가 일기 + 30초 나레이션 대본을 생성하고, 승인 후 Live2D/VRM 아바타 영상으로 저장하는 서비스. 위치 기반 메시지, 개인 맞춤 상담, 캘린더/이력 조회 포함.

- Frontend: **Streamlit** (`frontend/`)
- Backend: **FastAPI** (`bakcend/`) — 폴더명이 오타지만 현재 구조 유지 중
- DB: **Naver Cloud DB for MySQL** / 미디어는 **Naver Object Storage**
- AI: **CLOVA Studio / Speech / Voice / OCR / Vision**
- 지도: **Naver Maps** / 인프라: **Naver Cloud Platform (NCP)**

## 디렉터리 구조와 코드 배치 규칙

```
frontend/
├─ src/          # 공용 컴포넌트
├─ pages/        # 화면 단위: diary, counsel, calendar, map
└─ api/          # 백엔드 API 호출 클라이언트 (UI에서 직접 HTTP 호출 금지)

bakcend/
├─ api/          # FastAPI 라우터. 기능별 파일 분리 (diary, counsel, calendar, location, jobs)
├─ orchestration/# 에이전트 오케스트레이터 (호출 순서, 재시도, 분기)
├─ agents/       # 에이전트 로직. 한 에이전트 = 한 폴더
│  ├─ diary_chatbot/
│  ├─ counsel_chatbot/
│  └─ history_agent/
├─ services/     # 외부 서비스 어댑터: avatar, speech(STT/TTS), storage, maps
└─ config.py     # 설정. 비밀값은 환경변수로만

database/
├─ migrations/   # 스키마 변경 이력
└─ conn/         # DB 연결 관리
```

**배치 원칙**
- 외부 AI/클라우드 서비스(CLOVA, Object Storage, Maps) 호출은 반드시 `bakcend/services/` 어댑터를 통한다. 에이전트나 라우터에서 SDK를 직접 호출하지 않는다. (모델·서비스 교체 가능성 확보)
- 에이전트 간 직접 호출 금지 — 흐름 제어는 `orchestration/`이 담당한다.
- Streamlit 페이지에서 DB 직접 접근 금지 — 항상 백엔드 API를 경유한다.

## 핵심 개발 원칙 (PRD 10.3 — 반드시 준수)

1. **구조화된 출력**: 에이전트 생성 결과는 항상 구조화된 스키마(Pydantic 모델)로 반환한다. 자유 텍스트 반환 금지.
2. **승인 게이트**: 사용자 승인(`DiaryVersion.approved`) 전에는 최종 저장·영상 생성(TTS/렌더링)을 절대 진행하지 않는다. `POST /diary/{id}/render`는 승인된 버전에만 동작해야 한다.
3. **어댑터 계층**: 외부 AI 호출은 어댑터로 분리 — 인터페이스를 먼저 정의하고 구현체를 갈아끼울 수 있게 한다.

## 데이터 취급 규칙

- **미디어 파일**(사진·음성·영상)은 Object Storage에 저장하고, DB에는 URL·해시·크기·MIME type만 저장한다. DB에 BLOB 저장 금지.
- **모델 입력 최소화**: LLM 호출 시 필요한 최소 데이터만 포함한다. 상담·일기 데이터 교차 사용은 사용자 동의 범위(`consent_scope`) 내로 제한한다.
- **삭제**: 사용자 삭제 요청 시 DB 레코드와 연결된 Object Storage 파일을 함께 삭제한다.
- **로깅(AgentLog)**: 원문 전체를 남기지 않는다. trace ID, 모델 버전, 처리 시간, 결과 코드 중심으로 기록하고 민감 내용은 마스킹한다.
- `.env`는 커밋 금지. 새 환경변수 추가 시 `.env.example`에 키만 추가한다.

## 비동기 작업 패턴

AI 생성(요약·대본)과 영상 렌더링은 **비동기 작업**으로 처리한다.
- 생성 요청은 즉시 작업 ID를 반환 (`POST /diary/{id}/generate` → job_id)
- 상태는 `GET /jobs/{job_id}`로 조회 (대기/처리중/완료/실패 + 진행률·실패 사유)
- 렌더링은 **멱등키**로 중복 방지 (`POST /diary/{id}/render`)
- 일반 API는 95% 요청 2초 이내 목표 — 무거운 작업을 동기 엔드포인트에 넣지 않는다.

## 안전 규칙 (상담사 에이전트)

상담 기능 코드를 작성·수정할 때 다음을 절대 완화하지 않는다:
- 진단명 단정, 약물·치료 지시, 과도한 의존 유도 표현 **차단** (C-02)
- 자해·타해 등 위기 표현 탐지 시 일반 상담 흐름을 **중단**하고 안전 안내 우선
- 페르소나: "의사가 아닌, 상담해주는 친구"
- 과거 이력 응답은 반드시 근거(일기 카드/날짜)를 제시하고, 기록이 없으면 추측하지 않고 "확인 가능한 기록 없음"으로 응답 (H-02)
- 위치 메시지 잠금 해제는 클라이언트 판단이 아닌 **서버 측 거리 검증**으로만 수행

## 코딩 컨벤션

**Backend (Python / FastAPI)**
- Python 3.11+, 타입 힌트 필수, Pydantic v2 스키마 사용
- 파일·함수: `snake_case`, 클래스: `PascalCase`
- 라우터는 기능별 분리, 엔드포인트는 README의 API 설계표를 따른다
- 예외는 삼키지 않는다 — 실패 사유를 작업 상태에 기록하고 재시도 가능하게

**Frontend (Streamlit)**
- 화면은 `pages/` 아래 메뉴 단위(diary, counsel, calendar, map)로 배치
- 각 화면은 PRD의 필수 상태를 모두 처리: 빈 화면 / 업로드중 / 생성중 / 수정중 / 완료 / 실패 등
- API 호출은 `frontend/api/` 클라이언트 모듈로 모은다

**공통**
- 요구사항 ID(D-01~09, L-01~04, C-01~03, H-01~02, K-01~02)를 커밋 메시지·PR·주석에서 참조한다
- 커밋 메시지는 "무엇을 왜" 중심으로 간결하게 (한국어/영어 무관)

## 테스트

- 기능 테스트: 요구사항 ID별 정상·실패·재시도 시나리오
- 멀티모달 엣지 케이스: 긴 음성, 흐린 사진, OCR 실패, 중복 파일, 시간 정보 누락
- AI 평가: 사실 일치, 요약 누락, 감정 과도 해석, 대본 길이, 사용자 수정 반영
- 보안: 파일 형식 위장, 프롬프트 인젝션
- 상담 안전: 자해·타해, 의료 질문, 의존 유도, 개인정보 노출, 근거 없는 추론

## 역할 분담 (작업 영역 참고)

| 담당 | 영역 | 주요 코드 위치 |
|------|------|----------------|
| 민진홍 | 캘린더 DB | `database/`, `bakcend/api/`(calendar) |
| 김수만 | 일기 챗봇 | `bakcend/agents/diary_chatbot/` |
| 김나형 | 일기 챗봇 | `bakcend/agents/diary_chatbot/` |
| 권예원 | 상담가 챗봇 | `bakcend/agents/counsel_chatbot/` |
