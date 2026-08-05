# Mediary Frontend (Streamlit)

Streamlit 기반 프론트엔드. 사이드바에서 4개 페이지(일기 채팅, 나만의 상담사, 캘린더 조회, 지도 조회)로 이동한다.

## 실행 방법

```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

## 폴더 구조

```
frontend/
├─ app.py              # 엔트리포인트. st.navigation으로 사이드바 페이지 라우팅
├─ requirements.txt    # FE 의존성 (streamlit)
├─ pages/              # 화면 단위 페이지 (사이드바 메뉴 1개 = 파일 1개)
│  ├─ diary.py         #   📔 일기 채팅 — 멀티모달 입력, 초안 편집, 영상 플레이어 (예정)
│  ├─ counsel.py       #   💬 나만의 상담사 — 상담 채팅, 참조 일기, 안전 안내 (예정)
│  ├─ calendar.py      #   📅 캘린더 조회 — 월간 캘린더, 날짜 상세, 감정 필터 (예정)
│  └─ map.py           #   🗺️ 지도 조회 — 위치 메시지 핀, 잠금 상태, 재생 (예정)
├─ src/                # 공용 컴포넌트·유틸 (여러 페이지에서 재사용하는 UI 조각)
└─ api/                # 백엔드 API 클라이언트 (페이지에서 직접 HTTP 호출 금지, 여기로 모은다)
```

## 규칙

- 새 화면은 `pages/`에 파일을 추가하고 `app.py`의 `pages` 리스트에 `st.Page`로 등록한다.
- 백엔드 호출은 반드시 `api/` 모듈을 경유한다 (페이지 코드에 requests 직접 사용 금지).
- 각 페이지는 PRD의 필수 상태(빈 화면/업로드중/생성중/수정중/완료/실패 등)를 처리해야 한다.
