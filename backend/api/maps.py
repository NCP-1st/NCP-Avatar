"""지도 일기 API 라우터 (L-01: 위치 기반 일기 저장/조회)."""

from fastapi import APIRouter

from backend.services.maps import DiaryPin, DiaryPinCreate, DiaryStore

router = APIRouter(prefix="/maps", tags=["maps"])

_store = DiaryStore()


@router.get("/diaries", response_model=list[DiaryPin])
def list_diaries() -> list[DiaryPin]:
    return _store.list_diaries()


@router.post("/diaries", response_model=DiaryPin, status_code=201)
def create_diary(payload: DiaryPinCreate) -> DiaryPin:
    return _store.add_diary(payload)
