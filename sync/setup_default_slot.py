"""
setup_default_slot.py — 在 DB1 新增 Default_Slot 欄位，並從 Current_Slot 初始化

只需執行一次。執行後請在 Notion 手動確認並調整各球員的 Default_Slot。
"""
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from notion_config import NOTION_KEY_PATH, DB_PLAYERS

SLOT_OPTIONS = ["C", "1B", "2B", "3B", "SS", "OF", "Util", "BN", "IL"]


def load_notion_key() -> str:
    return Path(NOTION_KEY_PATH).expanduser().read_text().strip()


def notion_headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def add_default_slot_property(key: str) -> None:
    """在 DB1 新增 Default_Slot Select 欄位（若已存在，Notion 會忽略）"""
    url = f"https://api.notion.com/v1/databases/{DB_PLAYERS}"
    body = {
        "properties": {
            "Default_Slot": {
                "select": {
                    "options": [{"name": s} for s in SLOT_OPTIONS]
                }
            }
        }
    }
    r = requests.patch(url, headers=notion_headers(key), json=body)
    r.raise_for_status()
    print("✓ Default_Slot 欄位已新增到 DB1")


def init_default_slot_from_current(key: str) -> None:
    """把每個 My Roster 球員的 Default_Slot 初始化為當前 Current_Slot"""
    url = f"https://api.notion.com/v1/databases/{DB_PLAYERS}/query"
    body: dict = {
        "page_size": 100,
        "filter": {"property": "Player_Type", "select": {"equals": "My Roster"}},
    }
    pages = []
    while True:
        r = requests.post(url, headers=notion_headers(key), json=body)
        r.raise_for_status()
        data = r.json()
        pages.extend(data["results"])
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break

    print(f"共 {len(pages)} 位球員，初始化 Default_Slot...\n")
    for page in pages:
        props = page["properties"]
        title_list = props["Name"]["title"]
        name = title_list[0]["plain_text"] if title_list else "?"
        current_slot = (props["Current_Slot"]["select"] or {}).get("name", "BN")

        patch_url = f"https://api.notion.com/v1/pages/{page['id']}"
        r = requests.patch(
            patch_url,
            headers=notion_headers(key),
            json={"properties": {"Default_Slot": {"select": {"name": current_slot}}}},
        )
        r.raise_for_status()
        print(f"  {name:<28} Default_Slot = {current_slot}")


def main():
    key = load_notion_key()

    print("=== Step 1: 新增 Default_Slot 欄位 ===")
    add_default_slot_property(key)
    print()

    print("=== Step 2: 從 Current_Slot 初始化 ===")
    init_default_slot_from_current(key)

    print("\n完成！請在 Notion 手動確認各球員的 Default_Slot。")
    print("（投手的 Default_Slot 保持 SP/RP/P，BN/IL 球員保持 BN/IL，不影響換人邏輯）")


if __name__ == "__main__":
    main()
