# 상담사 챗봇 설계

요구사항 ID: C-01(개인화 검색) · C-02(안전 규칙) · C-03(기억 제어) · H-02(근거 제시)

## 어디에 무엇이 있나

상담 기능은 프로젝트 구조를 따라 흩어져 있다. **이 폴더에는 에이전트만 있다.**

| 위치 | 역할 |
|------|------|
| `backend/api/counsel.py` | 엔드포인트 `POST /api/counsel/chat` |
| `backend/orchestration/counsel_flow.py` | **흐름 전체** — 호출 순서·재시도·안전 분기 |
| `backend/agents/counsel_chatbot/` | 두 에이전트 + 안전·스타일·프롬프트·스키마 |
| `backend/services/knowledge/` | 온톨로지 RAG 어댑터 (상담 지식 / 개인 관계) |
| `backend/repositories/` | 대화 이력 저장소 (`ConversationStore`) |
| `backend/dependencies.py` | 의존성 조립 — 스텁을 실제 구현으로 바꾸는 지점 |

## 흐름

```
                          채팅 질의(텍스트)
                                │
                    ┌───────────┴────────────┐
                    ▼                        ▼
            대화 이력 저장            안전 선검사 ── 위기 ──▶ 안전 안내 (모델 호출 없음)
          (ConversationStore)              │
                                           ▼
                              ┌────────────────────────┐
                              │  ContextAgent          │  CLOVA Studio
                              │  사건 + 감정 구조화     │
                              └───────────┬────────────┘
                                          │ ConversationState
                              ┌───────────┴───────────┐
                              ▼                       ▼
                       CounselKnowledge        PersonalOntology
                        상담 지식 RAG            관계 정보 RAG
                              │                       │
                              └───────────┬───────────┘
                                          ▼
                              ┌────────────────────────┐
                              │  CounselorAgent        │  CLOVA Studio
                              │  공감·반영·질문·행동    │
                              └───────────┬────────────┘
                                          ▼
                              출력 안전 검사 ── 위반 ──▶ 1회 재생성 ──▶ 안전 폴백
                                          ▼
                              근거 카드 매핑 → 응답 저장 → 반환
```

검색 두 갈래는 `asyncio.gather`로 동시에 돈다. 순차로 하면 왕복이 그대로 쌓인다.

> **과거 이력 조회(일기 검색)는 아직 없다.** 붙일 때 `counsel_flow`에 세 번째
> 갈래로 추가하고, `safety.review_past_claims` 검사를 "검색 결과가 없을 때만"
> 걸도록 되돌려야 한다. 지금은 참고할 기록이 아예 없어 항상 건다.

## 이 폴더의 파일

| 파일 | 역할 |
|------|------|
| `context_agent.py` | 챗봇 에이전트 — 사건·감정 구조화 |
| `counselor_agent.py` | 상담가 에이전트 — 답변 초안 |
| `safety.py` | 입력 위기 탐지 + 출력 금칙 검사 + 안내 번호 (C-02) |
| `style.py` | 응답 스타일 검사 (길이·질문 수·불릿·이모지·공감 반복) |
| `prompts.py` | 두 에이전트의 시스템 프롬프트 |
| `schemas.py` | 구조화 출력 스키마 |

두 에이전트는 서로를 부르지 않는다. 전부 `orchestration/counsel_flow.py`가
부른다.

## 실행

```bash
uvicorn backend.main:app --port 8000      # 백엔드
cd frontend && streamlit run app.py       # 프론트엔드
```

엔드포인트는 `POST /api/counsel/chat`이다.

추가로 필요한 패키지: `langchain-naver` (backend), `requests` (frontend).

> `langchain-naver`는 기존 `backend/services/llm/factory.py`가 이미 쓰고 있는데
> `backend/requirements.txt`에 빠져 있다. 상담 기능과 무관한 기존 누락이라
> 여기서 고치지 않았다.

## 아직 스텁인 것

전부 `backend/dependencies.py` 아래쪽 네 줄이 교체 지점이다. 그것만 바꾸면
되고 에이전트·흐름 코드는 손대지 않는다.

| 변수 | 현재 스텁 | 실제 구현 |
|------|-----------|-----------|
| `counsel_store` | `InMemoryConversationStore` | MySQL — `counsel_sessions` + 턴 테이블 |
| `counsel_knowledge` | `InMemoryCounselKnowledge` | 상담 가이드라인 지식베이스 |
| `counsel_ontology` | `InMemoryPersonalOntology` | 개인 온톨로지(그래프) |

`database/models.py`에 `CounselSession`이 이미 있다. 대화 턴을 담을 테이블만
추가하면 `ConversationStore`를 MySQL로 구현할 수 있다.

과거 이력 조회(C-01/H-01/H-02)는 아직 붙이지 않았다. 상담가 프롬프트는 "참고할
과거 기록이 주어지지 않는다"를 전제로 쓰여 있으므로, 붙일 때 그 절도 함께
고쳐야 한다.

## 설계상 지켜야 할 것

- **위기 표현이 잡히면 모델을 부르지 않는다.** 안전을 모델 판단에 걸지 않고
  하드코딩된 안내로 대체한다.
- **대화 이력은 서버가 보관한 것만 믿는다.** 클라이언트가 보낸 이력을 그대로
  쓰면 이력을 위조해 안전 규칙을 우회할 수 있다.
- **기억 제어(C-03)** 는 지금 관계 정보(개인 온톨로지)에만 걸린다. 일기 검색이
  붙으면 그쪽에도 같이 적용해야 한다.
- **검색 한 갈래가 죽어도 상담은 계속된다.** 검색 실패가 상담 실패가 되면 안 된다.
- **위기가 한 번 감지된 세션은 끝까지 위기 세션이다.** 사용자가 화제를 돌려도
  정리·제안 단계로 올리지 않는다. 위기 다음 턴에 "따뜻한 차 한 잔 어떠세요"가
  나가면 안 된다. `ConversationStore.is_crisis`로 확인한다.
- **위기 안내는 종류별로 다르다.** 임박(시점·수단·시도) > 타해 > 자해 사고
  순으로 우선하며, 안내 번호는 `safety.HELPLINES`에 모아 둔다. 변경 이력이
  있는 값이라 코드에 흩뿌리지 않는다.
- **상담 지식과 개인 관계는 따로 검색한다.** 섞으면 모델이 일반론을 그 사람
  개인사인 것처럼 말한다. `observed: false`(추론)와 사실 구분도 프롬프트까지
  넘긴다.

## 구조화 출력에서 반복해 밟은 함정

**Pydantic 필드에 기본값을 주면 JSON Schema의 `required`에서 빠지고, 모델이
그 필드를 통째로 생략한다.** `intensity`가 항상 3, `confidence`가 항상 0.0,
`events`가 항상 빈 배열로 나오던 원인이 전부 이것이었다. 모델이 반드시 채워야
하는 필드에는 기본값을 주지 않는다. 대신 "없으면 빈 배열"을 description에 적는다.

또한 숫자 필드는 척도를 프롬프트에 명시해야 한다. "확신이 없으면 낮추세요"만
있으면 모델은 계속 0.0을 낸다.

반대로 모델은 범위를 벗어난 값도 낸다(`intensity: -1`). 그때 턴 전체를
실패시키지 않도록 `EmotionReading`은 검증 대신 clamp한다.

## 알려진 한계

- 감정 라벨은 `EMOTION_LABELS` 고정 목록이다. 목록 밖 라벨이 나오면 중립으로
  떨어뜨리고 확신도를 낮춘다. `emotion label out of range` 경고가 쌓이면
  목록에 추가해야 한다는 신호다. **일기 챗봇의 감정 태그와 같은 어휘를 써야
  검색이 맞물린다** — 합칠 때 맞춰야 한다.
- LLM을 두 번 부르므로 한 턴에 7초 안팎이 걸린다. 줄이려면 사건·감정 구조화를
  답변 생성에 합치고 검색은 직전 턴 결과를 쓰는 방법이 있는데, 그러면 감정이
  한 턴 늦게 반영된다.
- 위기·주의 키워드는 정규식이라 오탐이 난다. 미탐 비용이 더 크다고 보고
  재현율을 택했다. 실제 사용자 문장으로 평가셋을 만들어 조정해야 한다.
  완곡 표현("다 끝내고 싶다")까지 넣었지만 변형은 계속 나올 수 있다.
- 음악은 특정 곡·가수 대신 분위기로 권한다. 존재하지 않는 곡을 추천하는 게
  가장 나쁜 실패라서다. 곡 DB가 붙으면 바꿀 수 있다.
- 위기 세션 사후 리뷰 큐는 아직 없다. 지금은 `crisis_redirect` 결과 코드와
  경고 로그만 남는다.
