"""위치 기반 일기 mock 저장소 — JSON 파일 기반.

DB(Naver Cloud MySQL) 연동 전까지 쓰는 임시 구현.
인터페이스(list_diaries/add_diary)를 유지한 채 구현체만 교체한다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backend.services.maps.schemas import DiaryPin, DiaryPinCreate

_DATA_PATH = Path(__file__).parent / "data" / "mock_diaries.json"


class DiaryStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else _DATA_PATH

    def list_diaries(self) -> list[DiaryPin]:
        return [DiaryPin.model_validate(d) for d in self._load()]

    def add_diary(self, data: DiaryPinCreate) -> DiaryPin:
        diaries = self._load()
        pin = DiaryPin(
            id=self._next_id(diaries),
            date=date.today().isoformat(),
            **data.model_dump(),
        )
        diaries.append(pin.model_dump())
        self._save(diaries)
        return pin

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        with self._path.open(encoding="utf-8") as f:
            return json.load(f).get("diaries", [])

    def _save(self, diaries: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump({"diaries": diaries}, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _next_id(diaries: list[dict]) -> str:
        nums = [
            int(d["id"][1:])
            for d in diaries
            if d.get("id", "").startswith("d") and d["id"][1:].isdigit()
        ]
        return f"d{(max(nums) + 1) if nums else 1:03d}"
