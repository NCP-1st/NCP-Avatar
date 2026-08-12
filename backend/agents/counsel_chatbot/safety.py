
from __future__ import annotations

import os
import re
from typing import NamedTuple

from backend.agents.counsel_chatbot.schemas import SafetyLevel


# --- 입력 선검사 -----------------------------------------------------------
_CRISIS_PATTERNS: dict[str, re.Pattern[str]] = {
    # 시점·수단·실행 의사가 드러나거나 이미 시도한 경우.
    #
    # 시점 표현은 죽음·종결 의사와 붙어 있을 때만 잡는다. "오늘 다 끝낼"은
    # 위기지만 "오늘 일 다 끝냈어요"는 아니다. 어미(끝낼 / 끝냈)로 갈린다.
    "imminent": re.compile(
        r"(오늘|내일|이따|지금)[^.!?]{0,10}(죽|자살|다\s*끝낼|다\s*끝내고\s*싶)"
        r"|약을?\s*(모아|모았|다\s*먹)|유서를?\s*(썼|쓰고|남겨)"
        r"|(자살|자해)(를|을)?\s*(시도|해\s*봤|한\s*적)|시도했었"
        r"|손목을?\s*(그었|그은)"
        r"|다\s*준비(했|해\s*놨)|(옥상|난간)에\s*(올라|서\s*있)"
    ),
    "harm_others": re.compile(r"죽여\s*버리|죽이고\s*싶|해치고\s*싶|다\s*죽여"),
    "self_harm": re.compile(
        r"자살|자해|극단적\s*선택|목숨을?\s*끊|목\s*을?\s*매|손목을?\s*긋"
        r"|죽고\s*싶|죽어\s*버리|뛰어내리|유서|번개탄"
        # 완곡한 표현. 실제로는 이쪽이 더 자주 쓰인다.
        r"|다\s*끝내(고\s*싶|버리)|모든\s*(걸|것을)\s*끝내|다\s*끝낼\s*(거|게|래)"
    ),
    "disappear": re.compile(r"사라지고\s*싶|없어지고\s*싶|태어나지\s*말았어야"),
}

_CAUTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "give_up": re.compile(r"다\s*그만두고\s*싶|포기하고\s*싶|버티기\s*힘들|의미가\s*없"),
    "panic": re.compile(r"공황|숨이\s*안\s*쉬어|숨을\s*못\s*쉬"),
    "substance": re.compile(r"술\s*없이는|매일\s*술|약\s*없이는\s*못"),
    "isolation": re.compile(r"아무도\s*없|혼자\s*뿐|말할\s*사람이\s*없"),
}


class SafetyScreening(NamedTuple):
    level: SafetyLevel
    matched_rules: list[str]


def screen_user_message(text: str) -> SafetyScreening:
    """사용자 입력의 안전 등급을 판정한다."""
    crisis = [name for name, pat in _CRISIS_PATTERNS.items() if pat.search(text)]
    if crisis:
        return SafetyScreening(SafetyLevel.CRISIS, crisis)

    caution = [name for name, pat in _CAUTION_PATTERNS.items() if pat.search(text)]
    if caution:
        return SafetyScreening(SafetyLevel.CAUTION, caution)

    return SafetyScreening(SafetyLevel.NORMAL, [])


# --- 출력 검사 -------------------------------------------------------------

_DIAGNOSIS_TERMS = (
    r"우울증|조울증|양극성\s*장애|공황장애|불안장애|강박증|조현병|ADHD"
    r"|경계선\s*인격장애|외상\s*후\s*스트레스|PTSD|번아웃\s*증후군"
)

_OUTPUT_PATTERNS: dict[str, re.Pattern[str]] = {
    # "당신은 우울증입니다", "공황장애로 보입니다" 처럼 단정하는 문장
    "diagnosis": re.compile(
        rf"({_DIAGNOSIS_TERMS})\s*(이|가|으로|로)?\s*"
        r"(입니다|이에요|예요|이야|인\s*것\s*같|의심|진단|증상입니다|이신\s*것)"
        rf"|진단(해|하)\s*(드리|줄|보면)|({_DIAGNOSIS_TERMS})\s*환자"
    ),
    # 약물·치료 지시
    "medical_advice": re.compile(
        r"항우울제|신경안정제|수면제|정신과\s*약|처방"
        r"|약을?\s*(드세요|먹어요|먹어봐|복용|끊|늘리|줄이)"
        r"|병원에?\s*가지\s*마|치료를?\s*받지\s*마|상담을?\s*그만"
    ),
    # 과도한 의존 유도
    "dependency": re.compile(
        r"나만\s*믿|나\s*없이는|나에게만\s*말|나한테만\s*얘기"
        r"|다른\s*사람(에게|한테)(는)?\s*말하지\s*마"
        r"|(나는|내가)\s*항상\s*(너의|네)\s*곁"
        r"|매일\s*나(와|랑)\s*(만\s*)?(얘기|대화)해"
    ),
}


def review_reply(text: str) -> list[str]:
    """모델 답변에서 금칙 표현을 찾아 위반 규칙 이름을 돌려준다."""
    return [name for name, pat in _OUTPUT_PATTERNS.items() if pat.search(text)]


_PAST_CLAIM_PATTERN = re.compile(
    r"매번|늘\s*그[래렇]|항상\s*그[래렇]|예전에도|이전에도|저번에도|지난번에도"
    r"|평소에도|반복(적으로|해서|되)"
    r"|(자주|종종|계속)\s*\S*(하시는|느끼시는|겪으시는|그러시는)"
    r"|(예전|과거|저번|지난\s*번)에\s*(도|는)?\s*\S*(하셨|셨)"
)

# 시점을 특정하는 표현. "요즘"·"가끔"처럼 범위가 흐린 말은 넣지 않는다 —
# 사실을 단정하는 게 아니라 인상을 말하는 것이라 지어냈다고 볼 수 없다.
_TIME_ANCHOR = re.compile(
    r"지난\s*주|지난\s*달|지난\s*해|지난번|저번|엊그제|그제|어제|며칠\s*전"
    r"|얼마\s*전|작년|재작년|올해\s*초|\d{1,2}\s*월\s*\d{1,2}\s*일"
    r"|\d{1,2}\s*일\s*전|\d{1,2}\s*주\s*전|\d{1,2}\s*년\s*전"
)
_PAST_TENSE = re.compile(r"셨|했|였|었")
# 묻는 문장은 단정이 아니다. "그때 어떤 상황이 힘들게 했나요?"를 막으면
# 상담사가 과거를 물어볼 수가 없다.
#
# 물음표에만 의존하면 안 된다. 모델은 "지난주에는 어떠셨나요." 처럼 마침표로
# 끝내기도 하는데, 그걸 단정으로 보면 멀쩡한 질문이 폴백 문구로 바뀐다.
# 그래서 끝의 문장부호를 떼고 어미로 판정한다.
_QUESTION_MARK = re.compile(r"[?？]")
_QUESTION_ENDING = re.compile(r"(나요|까요|세요|을까|ㄹ까|은지|는지)$")
_TRAILING_PUNCT = re.compile(r"[.!?？。…\s]+$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def review_past_claims(text: str, *, grounded: str = "") -> list[str]:
    """근거 없는 과거 단정을 찾는다.

    검색된 일기가 하나도 없을 때만 부른다. 일기가 있으면 과거를 말할 근거가
    있는 것이므로 이 검사를 걸면 안 된다.

    두 가지를 본다.

    1. 습관·반복 단정("매번", "늘 그러시죠"). 한 번 들은 이야기로 "늘 그렇다"고
       일반화하는 건 일기가 있든 없든 상담사가 알 수 없는 것이다.
    2. **대화에 없는 시점**을 과거 사실로 단정하는 것. `grounded`에는 이 대화에서
       사용자가 한 말을 넘긴다.

    2번에 근거 대조가 필요한 이유는 실측으로 확인했다. 시점 표현과 과거 어미만
    보고 잡으면 운영 답변 37건 중 걸린 3건이 **전부 오탐**이었다 — 사용자가
    "지난주에 친구들이랑 놀러 갔다"고 말한 뒤의 "지난주에 친구분들과 시간을
    보내셨죠"는 지어낸 게 아니라 감정 반영이고, "그때 어떤 상황이 힘들게
    했나요?"는 아예 질문이다. 상담사가 스스로 꺼낸 시점만 문제가 된다.

    `grounded`를 비워 두면 사용자가 아무 말도 안 한 것으로 보고 시점 표현을
    전부 근거 없음으로 판정한다. 호출부는 반드시 대화를 넘겨야 한다.

    사용자 발화만 근거로 친다. 상담사가 앞 턴에서 한 말을 근거로 삼으면, 한 번
    지어낸 과거가 다음 턴부터 사실로 굳는다.
    """
    if _PAST_CLAIM_PATTERN.search(text):
        return ["past_speculation"]

    haystack = re.sub(r"\s+", "", grounded)
    for raw in _SENTENCE_SPLIT.split(text):
        raw = raw.strip()
        # 물음표는 원문에서, 어미는 부호를 뗀 쪽에서 본다. 순서를 바꾸면
        # "어떠셨어요?" 가 부호를 잃고 단정으로 넘어간다.
        sentence = _TRAILING_PUNCT.sub("", raw)
        if not sentence or _QUESTION_MARK.search(raw):
            continue
        if _QUESTION_ENDING.search(sentence):
            continue
        if not _PAST_TENSE.search(sentence):
            continue
        for anchor in _TIME_ANCHOR.findall(sentence):
            if re.sub(r"\s+", "", anchor) not in haystack:
                return ["past_fabrication"]
    return []


# --- 안내 문구 -------------------------------------------------------------


# TODO: 공용 `backend/config.py`가 상담 설정을 받게 되면 그쪽으로 옮긴다.
HELPLINES: dict[str, str] = {
    "suicide": os.getenv("COUNSEL_HELPLINE_SUICIDE", "109"),
    "mental_health": os.getenv("COUNSEL_HELPLINE_MENTAL", "1577-0199"),
    "youth": os.getenv("COUNSEL_HELPLINE_YOUTH", "1388"),
    "women": os.getenv("COUNSEL_HELPLINE_WOMEN", "1366"),
    "emergency": os.getenv("COUNSEL_HELPLINE_EMERGENCY", "119"),
}


CRISIS_NOTICE = (
    "지금 많이 힘든 상태로 보여요. 저는 의료·위기 상담을 대신할 수 없어서, "
    "아래로 바로 연락해 주시면 좋겠어요.\n\n"
    f"- 자살예방 상담전화 **{HELPLINES['suicide']}** (24시간, 비밀 보장)\n"
    f"- 정신건강 위기상담전화 **{HELPLINES['mental_health']}** (24시간)\n"
    f"- 청소년 상담전화 **{HELPLINES['youth']}**\n"
    f"- 여성긴급전화 **{HELPLINES['women']}**\n"
    f"- 급박한 위험이라면 **{HELPLINES['emergency']}**\n\n"
    "가까운 사람에게 지금 상태를 알리는 것도 도움이 돼요."
)

# 템플릿 A — 자살·자해 사고 언급
CRISIS_MESSAGE = (
    "지금 많이 힘드신 것 같아요. 이런 얘기를 꺼내주신 것만으로도 큰 일을 하신 거예요.\n\n"
    "제가 드릴 수 있는 것보다, 지금은 사람과 직접 이야기하시는 게 훨씬 도움이 될 것 "
    f"같아요. 자살예방 상담전화 {HELPLINES['suicide']}번은 24시간 운영되고 비밀이 "
    "보장돼요. 전화 한 통이면 됩니다.\n\n"
    "지금 안전한 곳에 계신가요?"
)

# 템플릿 B — 시점·수단·실행 의사가 드러나거나 이미 시도한 경우
IMMINENT_MESSAGE = (
    "지금 바로 도움이 필요한 상황으로 보여요.\n\n"
    f"지금 즉시 {HELPLINES['suicide']}(자살예방 상담전화)나 "
    f"{HELPLINES['emergency']}로 연락해 주세요. 두 곳 다 24시간 열려 있어요.\n"
    "가까이에 있는 사람에게 지금 옆에 있어달라고 말씀하시는 것도 좋습니다.\n\n"
    "저는 여기 계속 있을게요."
)

IMMINENT_NOTICE = (
    f"**{HELPLINES['emergency']}** 또는 **{HELPLINES['suicide']}** — 지금 연락해 주세요. "
    "24시간 운영됩니다."
)

# 템플릿 C — 타인 위해 언급
HARM_OTHERS_MESSAGE = (
    "지금 그만큼 화가 나신 상황인 것 같아요. 다만 이건 저와의 대화로 다룰 수 있는 "
    "범위를 넘어서는 것 같습니다.\n\n"
    f"정신건강 위기상담전화 {HELPLINES['mental_health']}나 가까운 "
    "정신건강복지센터에 연락해 보시면 좋겠어요."
)


def crisis_response(matched_rules: list[str]) -> tuple[str, str]:
    """위기 종류에 맞는 (메시지, 안내)를 고른다.

    한 발화에 여러 신호가 섞이면 더 급한 쪽을 쓴다. `_CRISIS_PATTERNS`의
    선언 순서가 곧 우선순위다.
    """
    if "imminent" in matched_rules:
        return IMMINENT_MESSAGE, IMMINENT_NOTICE
    if "harm_others" in matched_rules:
        return HARM_OTHERS_MESSAGE, CRISIS_NOTICE
    return CRISIS_MESSAGE, CRISIS_NOTICE

CAUTION_NOTICE = (
    "혹시 마음이 더 힘들어지면 자살예방 상담전화 **109** 또는 "
    "정신건강 상담전화 **1577-0199**에서 24시간 도움을 받을 수 있어요."
)

GUARDRAIL_FALLBACK = (
    "지금 이야기해 준 내용에 제대로 답하려다 보니 제가 넘지 말아야 할 선에 "
    "가까워졌어요. 대신 이렇게 정리해 볼게요.\n\n"
    "지금 느끼는 감정이 어떤 상황에서 가장 커지는지, 한 가지만 더 이야기해 줄 수 있을까요? "
    "저는 진단이나 치료 조언은 드릴 수 없지만, 마음을 정리하는 건 함께할 수 있어요.\n\n"
    "몸이나 마음의 증상이 계속된다면 전문가와 이야기해 보는 걸 권해요."
)

PAST_CLAIM_FALLBACK = (
    "이야기해 주셔서 고마워요. 지금 해주신 말씀만 놓고 보면 마음이 쉽지 않은 "
    "상태로 느껴져요.\n\n"
    "예전에는 어땠는지까지는 제가 확인할 수 있는 기록이 없어서 말씀드리기 "
    "어려워요. 지금 어떤 부분이 가장 크게 느껴지는지 조금 더 이야기해 "
    "주실 수 있을까요?"
)

LLM_FALLBACK = (
    "죄송해요, 지금 답변을 만들다가 문제가 생겼어요. "
    "잠시 뒤에 다시 이야기해 주시겠어요?"
)
