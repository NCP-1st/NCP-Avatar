from backend.agents.diary_chatbot.normalize import normalize_fact_extraction


def test_normalizer_supplies_defaults_and_ignores_model_coverage() -> None:
    result = normalize_fact_extraction(
        {
            "events": [{
                "event": "친구들과 집에서 치맥했다",
                "people": "친구들",
                "location": "집",
                # actions, emotions and evidence are intentionally omitted.
            }],
            "coverage": {"sufficient": True},
        },
        source_texts={"turn-1": "친구들과 집에서 치맥했다"},
        current_input_id="turn-1",
    )

    assert result.events[0].people == ["친구들"]
    assert result.events[0].actions == []
    assert result.events[0].emotions == []
    assert result.events[0].evidence[0].input_id == "turn-1"
    assert result.coverage.has_emotion is False
    assert result.coverage.sufficient is False
    assert result.coverage.missing_fields == ["emotion"]


def test_normalizer_rejects_unknown_provenance_and_unverified_emotion() -> None:
    result = normalize_fact_extraction(
        {
            "events": [{
                "event": "산책했다",
                "emotions": [{
                    "label": "행복함",
                    "excerpt": "행복했다",
                    "input_id": "invented-input",
                }],
                "evidence": [{"input_id": "invented-input"}],
            }],
        },
        source_texts={"turn-1": "산책했다"},
    )

    # The event itself can be tied uniquely to turn-1, but the invented emotion cannot.
    assert result.events[0].evidence[0].input_id == "turn-1"
    assert result.events[0].emotions == []
    assert result.coverage.has_emotion is False


def test_normalizer_keeps_only_observations_for_attached_images() -> None:
    result = normalize_fact_extraction(
        {
            "events": [],
            "image_observations": [
                {
                    "input_id": "photo-1",
                    "description": "테이블 위에 치킨과 맥주가 놓여 있다.",
                    "observed_facts": ["치킨", "맥주"],
                },
                {
                    "input_id": "invented-photo",
                    "description": "존재하지 않는 사진",
                },
            ],
        },
        source_texts={},
        image_input_ids={"photo-1"},
    )

    assert len(result.image_observations) == 1
    assert result.image_observations[0].input_id == "photo-1"
    assert result.image_observations[0].observed_facts == ["치킨", "맥주"]
