import json
import os
from typing import Dict

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_FILE = os.path.join(DATA_DIR, "emoji_like_config.json")
DEFAULT_EMOJI_ID = "123"


def _load_data() -> Dict[str, str]:
    if not os.path.exists(DATA_FILE):
        return {"emoji_id": DEFAULT_EMOJI_ID}

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            raw = json.load(f)
            if not isinstance(raw, dict):
                return {"emoji_id": DEFAULT_EMOJI_ID}
            emoji_id = str(raw.get("emoji_id", DEFAULT_EMOJI_ID)).strip()
            if not emoji_id.isdigit():
                emoji_id = DEFAULT_EMOJI_ID
            return {"emoji_id": emoji_id}
        except json.JSONDecodeError:
            print(f"警告：{DATA_FILE} 内容不是有效的JSON，将使用空数据。")
            return {"emoji_id": DEFAULT_EMOJI_ID}


def _save_data(data: Dict[str, str]):
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_emoji_id() -> str:
    data = _load_data()
    emoji_id = str(data.get("emoji_id", DEFAULT_EMOJI_ID)).strip()
    if not emoji_id.isdigit():
        return DEFAULT_EMOJI_ID
    return emoji_id


def set_emoji_id(emoji_id: str) -> None:
    value = str(emoji_id).strip()
    if not value.isdigit():
        raise ValueError("emoji_id must be numeric")
    _save_data({"emoji_id": value})

