# 테스트 전용 구조

이 디렉터리 아래 파일은 모두 테스트·평가·회귀 검증 전용이며 `backend/`와
`frontend/`의 런타임 코드에서 import하지 않는다.

| 경로 | 역할 |
|---|---|
| `agents/` | 정규화·감정 검증 등 에이전트 순수 로직 테스트와 목 응답 |
| `orchestration/` | 여러 턴 누적, 확인 게이트, 승인 게이트 테스트 |
| `dummy_pipeline/` | API·전처리·어댑터를 묶은 로컬 통합 테스트 |
| `architecture/` | 에이전트 직접 호출 및 테스트 패키지 역참조 방지 |
| `live/` | 실제 CLOVA API를 사용하는 opt-in 테스트 |
| `assets/` | 라이브·멀티모달 테스트용 사진과 음성 fixture |

운영 코드에 필요한 로컬 구현은 테스트 코드가 아니므로 다음 위치에 둔다.

- 인메모리 저장소: `backend/repositories/in_memory.py`
- 로컬 data URL 미디어 저장: `backend/services/storage/inline.py`
- 더미 STT: `backend/services/speech/dummy.py`

기본 테스트:

```bash
.venv/bin/python -m pytest -m "not live" -q
```

실제 API 테스트:

```bash
RUN_LIVE_LLM_TESTS=1 .venv/bin/python -m pytest tests/live -m live -vv -s
```
