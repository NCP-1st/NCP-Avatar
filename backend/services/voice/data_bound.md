
# 대본 생성을 위한 input

{
    "diary_id" : "test-diary-001",
    "diary_version_id" : "version-001",
    "diary" : {
        "title" : "일기 제목",
        "story" : " LLM이 생성한 일기 내용 ",
        "feelings" : ["즐거움", "편안함", "llm이 채팅을 통해서 감정을 추려냄.,"]
    },
    "chat_metadata" : {
        "people" : "사람",
        "places" : "장소",
        "events" : "사건",
        "dominant_feelings" : "주요 감정",
        "keywords" : "핵심"
    },
    "script_option" : {
        "target_duration_sec" : "보이스 생성 시간",
        "tone" : "원하는 음성 입력 톤",
        "speaker" : "화자 speaker"
    }

}

-----------------------------------------------------------------------

# 생성된 대본 결과
{
    "script_id" : "script_001",
    "diary_id" : "diary_id",
    "narration_text" : " 대본 ",
    "target_duration_seconds" : 30,
    "emotion" : 감정
}

-----------------------------------------------------------------------

# 음성 요청 input
{
    "script_id" : "script_001",
    "diary_id" : "diary_id",
    "text" :  "대본 내용" = "narration_text",
    "voice" : {
        "speaker" : " EMOTION_SUPPORTED_SPEAKERS 중 하나",
        "emotion" : " EMOTION_VALUES 중 하나",
        "emotion_strength" : "EMOTION_STRENGTH_VALUS 중 하나",
        "audio_format" : mp4
    }
}
