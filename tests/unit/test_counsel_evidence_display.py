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


def test_the_caption_says_it_looked_rather_than_cited() -> None:
    """`evidences`는 검색이 건져 온 목록이지 답변이 인용한 목록이 아니다.

    둘이 갈리는 일이 실제로 있었다 — "또 뭐 맛있게 먹었더라?"에 검색이 국밥
    일기를 다시 가져왔고, 상담사는 "국밥 외에는 기록이 없다"고 맞게 답했는데
    화면에는 "국밥 일기를 참고했어요"가 떴다. 없다면서 참고했다는 말이 된다.

    문구가 되돌아가면 같은 모순이 다시 보인다. 소스에서 `st.caption` 줄만
    떼어 보는 이유는 두 가지다 — Streamlit 페이지는 임포트만 해도 화면을
    그리고, 주석에 옛 문구가 예시로 남아 있어 전체 검색은 거기에 걸린다.
    """
    captions = [
        line.strip()
        for line in _SOURCE.splitlines()
        if line.strip().startswith("st.caption(f\"📖")
    ]

    assert len(captions) == 1, f"근거 캡션이 하나여야 한다: {captions}"
    assert "찾아봤어요" in captions[0]
    assert "참고했어요" not in captions[0]
