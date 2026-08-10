import base64
import io
import os
from pathlib import Path
import pytest
from dotenv import load_dotenv

pytest.importorskip("PIL", reason="라이브 비전 테스트에는 Pillow가 필요합니다")
pillow_heif = pytest.importorskip(
    "pillow_heif", reason="HEIC 라이브 테스트에는 pillow-heif가 필요합니다"
)
from PIL import Image

# 🔥 중요: Pillow 모듈 사용 및 Image.open() 호출 전 오프너 최상단 선언
pillow_heif.register_heif_opener()

# 프로젝트 최상위 루트 .env 강제 로드
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

from backend.agents.diary_chatbot.hcx import Hcx005MultimodalChatAgent
from backend.agents.diary_chatbot.models import MultimodalContext
from backend.config import load_config


def encode_image_to_data_url(image_path: str, max_dim: int = 1024) -> str:
    """
    CLOVA Studio 용량/해상도 제한 대응:
    이미지의 긴 축을 max_dim(기본 1024px)으로 비율에 맞게 리사이징 후 JPEG Base64로 인코딩
    """
    with Image.open(image_path) as img:
        rgb_img = img.convert("RGB")
        
        # 해상도가 max_dim보다 크면 비율 축소
        width, height = rgb_img.size
        if max(width, height) > max_dim:
            if width > height:
                new_w = max_dim
                new_h = int(height * (max_dim / width))
            else:
                new_h = max_dim
                new_w = int(width * (max_dim / height))
            rgb_img = rgb_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        rgb_img.save(buffer, format="JPEG", quality=85)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"

@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_LLM_TESTS") != "1",
    reason="유료 CLOVA Studio Vision API 호출 방지를 위해 RUN_LIVE_LLM_TESTS=1 필요",
)
@pytest.mark.anyio
async def test_hcx005_multimodal_food_extraction_live():
    config = load_config()
    if not config["llm"]["api_key"]:
        pytest.fail("CLOVA_STUDIO_API_KEY 설정이 필요합니다.")

    # 1. 음식 사진 경로 체크 (.HEIC, .jpg, .png 순서대로 탐색)
    sample_food_path = None
    candidates = [
        "tests/assets/sample_food.HEIC",
        "tests/assets/sample_image.HEIC",
        "tests/assets/sample_food.jpg",
        "tests/assets/sample_image.jpg",
    ]
    for path in candidates:
        if os.path.exists(path):
            sample_food_path = path
            break

    if not sample_food_path:
        pytest.fail("테스트에 사용할 사진 파일(tests/assets/sample_image.HEIC 또는 sample_image.jpg)이 필요합니다.")

    image_data_url = encode_image_to_data_url(sample_food_path)
    agent = Hcx005MultimodalChatAgent(config)

    # 2. 텍스트 + 음식 사진 동시에 전달
    context = MultimodalContext(
        session_id="vision-multimodal-food-test",
        user_message="건대에서 먹은건데 아주 맛있었어",
        text_inputs={"text-1": "건대에서 먹은건데 아주 맛있었어"},
        image_urls={"img-1": image_data_url},
    )

    # 3. Vision 멀티모달 해석 실행
    result = await agent.interpret(context)

    print("\n" + "=" * 50)
    print(f"📸 [사용된 테스트 이미지]: {sample_food_path}")
    print("🍕 [HCX-005 멀티모달(텍스트+음식사진) 분석 최종 결과]")
    print(result.model_dump_json(indent=2))
    print("=" * 50 + "\n")

    # 4. 정보 추출 및 맵핑 단정문(Assertion)
    assert result.model == config["llm"]["model_vision"]
    assert len(result.events) > 0

    # 라이브 테스트는 모델 변동성을 고려해 유효한 입력 근거가 하나 이상 연결되는지만 확인
    all_evidence_ids = [
        ev.input_id
        for event in result.events
        for ev in event.evidence
    ]
    assert any(evidence_id in {"text-1", "img-1"} for evidence_id in all_evidence_ids)
    assert set(all_evidence_ids) <= {"text-1", "img-1"}
