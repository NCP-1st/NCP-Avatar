TEXT_ONLY_LOCATION_MISSED = """
{
  "reaction": "건대에서 식사하셨군요.",
  "action_text": "",
  "events": [
    {
      "event": "건대에서의 식사 경험",
      "people": [],
      "location": null,
      "emotions": [{"label": "맛있었음", "excerpt": "맛있었어", "input_id": "text-1"}],
      "evidence": [
        {"input_id": "text-1", "excerpt": "건대에서 먹은건데 아주 맛있었어"}
      ]
    }
  ],
  "coverage": {
    "has_person": false,
    "has_location": false,
    "has_emotion": true,
    "missing_fields": [],
    "sufficient": true
  },
  "image_observations": [
    {
      "input_id": "img-1",
      "description": "음식이 담긴 접시가 보인다.",
      "observed_facts": ["음식", "접시"],
      "related_event": "건대에서의 식사 경험"
    }
  ],
  "follow_up_questions": []
}
"""
