# 일기 오케스트레이션 단계별 테스트

모든 명령은 프로젝트 루트에서 실행한다. 아래 1~6단계는 실제 CLOVA API를 호출하지 않으므로 `.env` 없이도 반복 실행할 수 있다.

## 0. 최초 1회 준비

```bash
cd "/Users/kwon-yewon/Desktop/e0ng/대외/2026_NaverCloud/NCP-Avatar"
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

이미 `.venv`가 준비되어 있으면 가상환경 생성과 설치는 생략한다.

## 1. 멀티턴 정보 수집 → 충분하면 종료

사람·장소·감정이 차례로 누적되고, 정보가 충분해지면 요약 확인 단계로 이동하는지 확인한다.

```bash
.venv/bin/python -m pytest \
  tests/orchestration/test_diary_context_loop.py::test_loop_stops_when_required_information_is_sufficient \
  -vv -s
```

## 2. 미확인 정보 재질문과 건너뛰기

미확인 필드는 횟수 제한 없이 다시 질문하고, 사용자가 현재 필드를 건너뛸 수 있는지 확인한다.

```bash
.venv/bin/python -m pytest \
  tests/integration/test_diary_workflow.py::test_same_missing_field_can_be_asked_until_confirmed \
  tests/integration/test_diary_workflow.py::test_user_can_skip_current_missing_field \
  -vv -s
```

## 3. 사용자 승인 게이트

승인 전에는 Voice 어댑터가 한 번도 호출되지 않는지 확인한다.

```bash
.venv/bin/python -m pytest \
  tests/orchestration/test_approval_gate.py::test_render_is_blocked_before_approval_without_calling_voice \
  -vv -s
```

승인된 버전은 렌더 경로로 진입하고, 아직 구현하지 않은 Voice stub의 `NotImplementedError`가 숨겨지지 않는지 확인한다.

```bash
.venv/bin/python -m pytest \
  tests/orchestration/test_approval_gate.py::test_approved_render_reaches_voice_stub_and_surfaces_not_implemented \
  -vv -s
```

## 4. 거절 후 새 버전 재생성

거절된 초안을 덮어쓰지 않고 새 `version_id`로 생성하며, 승인 전 렌더링은 시작하지 않는지 확인한다.

```bash
.venv/bin/python -m pytest \
  tests/orchestration/test_approval_gate.py::test_rejection_creates_new_version_without_rendering \
  -vv -s
```

## 5. 에이전트 연결 규칙과 로그 안전성

HCX-005 에이전트가 HCX-007 에이전트를 직접 호출하지 않고 오케스트레이터를 통하는지 정적 검사한다.

```bash
.venv/bin/python -m pytest tests/architecture/test_agent_isolation.py -vv
```

예외 로그에 사용자 원문과 예외 문자열이 저장되지 않는지 확인한다.

```bash
.venv/bin/python -m pytest \
  tests/integration/test_hcx_agents.py::test_interpret_failure_log_does_not_store_exception_message \
  -vv -s
```

## 6. 실제 API를 제외한 전체 회귀 테스트

```bash
.venv/bin/python -m pytest -m "not live" -q
```

성공 기준은 실패 없이 `passed`가 출력되는 것이다. `skipped`는 선택 의존성이나 opt-in 라이브 테스트일 수 있다.

## 7. CLOVA opt-in 라이브 스모크 테스트

`.env`에 실제 CLOVA 환경변수를 넣은 뒤 명시적으로 `live` 테스트를 실행한다. 테스트 코드가 `python-dotenv`로 `.env`를 직접 읽으므로 `source .env`는 하지 않아도 된다. API 비용과 네트워크 호출이 발생한다.

```bash
RUN_LIVE_LLM_TESTS=1 RUN_LIVE_STT_TESTS=1 \
  .venv/bin/python -m pytest tests/live -m live -vv -s
```

LLM만 확인하려면 다음 명령을 사용한다.

```bash
RUN_LIVE_LLM_TESTS=1 \
  .venv/bin/python -m pytest tests/live -m live -k "hcx005" -vv -s
```

STT만 확인하려면 `tests/assets/sample.wav`를 준비한 뒤 실행한다.

```bash
RUN_LIVE_STT_TESTS=1 \
  .venv/bin/python -m pytest tests/live/test_speech.py -m live -vv -s
```

라이브 테스트는 모델 응답의 정확한 문장보다 API 왕복 성공과 구조화된 응답 여부를 확인한다. 이미지 테스트가 의존성 때문에 건너뛰어지면 다음을 설치한 뒤 다시 실행한다.

```bash
.venv/bin/pip install Pillow pillow-heif
```
