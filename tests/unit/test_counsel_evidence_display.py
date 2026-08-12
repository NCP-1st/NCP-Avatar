"""근거 표시 문구를 만드는 부분만 따로 본다.

`strftime("%-m")`은 POSIX 전용이라 Windows Streamlit에서 그대로 터진다.
여기가 사용자에게 보이는 마지막 지점이라 날짜 포맷을 못 만들면 화면이 죽는다.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "frontend"))

# Streamlit 페이지는 임포트하는 것만으로 화면을 그린다. 포맷 함수만 떼어 온다.
_SOURCE = (
    Path(__file__).resolve().parents[2] / "frontend" / "pages" / "counsel.py"
).read_text(encoding="utf-8")
_NAMESPACE: dict = {"date": date}
exec(  # noqa: S102 - 페이지 전체를 실행하지 않고 함수 하나만 꺼내기 위해서다
    _SOURCE[
        _SOURCE.index("def format_diary_date") : _SOURCE.index("def render_evidences")
    ],
    _NAMESPACE,
)
format_diary_date = _NAMESPACE["format_diary_date"]


def test_same_year_omits_the_year() -> None:
    today = date.today()
    stamped = date(today.year, 8, 5)

    assert format_diary_date(stamped.isoformat()) == "8월 5일"


def test_other_year_keeps_the_year() -> None:
    """작년 일기를 '8월 5일'로만 쓰면 올해 것으로 읽힌다."""
    other = date.today().year - 1

    assert format_diary_date(f"{other}-08-05") == f"{other}년 8월 5일"


def test_no_zero_padding() -> None:
    """'08월 05일'은 한국어로 읽지 않는다."""
    today = date.today()

    assert format_diary_date(date(today.year, 1, 9).isoformat()) == "1월 9일"


def test_bad_input_raises_for_the_caller_to_handle() -> None:
    with pytest.raises(ValueError):
        format_diary_date("어제")
