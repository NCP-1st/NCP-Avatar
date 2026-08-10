from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.agents.diary_chatbot.write_script.agent import (
    write_script,
)
from backend.agents.diary_chatbot.write_script.schemas import (
    WriteScriptInput,
)
from backend.config import load_config

_SCRIPT_DIR = Path(__file__).resolve().parent
_TEST_DATA_PATH = _SCRIPT_DIR / "test.json"

async def main() -> None:
    config = load_config()

    raw_data = _TEST_DATA_PATH.read_text(encoding = "utf-8")
    script_input = WriteScriptInput.model_validate_json(raw_data)

    result = await write_script(
        script_input,
        config,
        script_id = "script_001"
    )

    print(
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
