"""
setup_db_week.py — 一次性：建立 DB_Week + 寫入 2026 整季週次 + 在 DB1 新增 14 個 schedule props
執行完後自動更新 notion_config.py 的 DB_WEEK ID

步驟：
  1. 建立 DB_Week（Title: Week_Number, Date: Week_Start）
  2. 寫入 W01–W26（共 26 週，從 2026-03-23 Mon 開始）
  3. PATCH DB1 新增 14 個 rich_text props（This_Mon～This_Sun, Next_Mon～Next_Sun）
  4. PATCH DB1 新增 Current_Week relation → DB_Week
  5. 更新 notion_config.py 的 DB_WEEK 值
"""
import sys
import re
import requests
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from notion_config import NOTION_KEY_PATH, DB_PLAYERS

PARENT_PAGE_ID    = "34048ad3-2a1c-80a0-bcaa-ca973c2d4100"
SEASON_FIRST_MONDAY = date(2026, 3, 23)  # 2026-03-25 開幕週的週一
TOTAL_WEEKS       = 26

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_notion_key() -> str:
    return Path(NOTION_KEY_PATH).expanduser().read_text().strip()


def notion_headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def create_db_week(key: str) -> str:
    url = "https://api.notion.com/v1/databases"
    body = {
        "parent": {"type": "page_id", "page_id": PARENT_PAGE_ID},
        "title": [{"type": "text", "text": {"content": "DB_Week"}}],
        "properties": {
            "Week_Number": {"title": {}},
            "Week_Start":  {"date": {}},
        },
    }
    r = requests.post(url, headers=notion_headers(key), json=body)
    r.raise_for_status()
    db_id = r.json()["id"]
    print(f"  DB_Week 建立成功：{db_id}")
    return db_id


def write_weeks(key: str, db_id: str) -> None:
    url = "https://api.notion.com/v1/pages"
    for i in range(TOTAL_WEEKS):
        week_start = SEASON_FIRST_MONDAY + timedelta(weeks=i)
        week_num   = f"W{i+1:02d}"
        body = {
            "parent": {"database_id": db_id},
            "properties": {
                "Week_Number": {"title": [{"text": {"content": week_num}}]},
                "Week_Start":  {"date": {"start": week_start.isoformat()}},
            },
        }
        r = requests.post(url, headers=notion_headers(key), json=body)
        r.raise_for_status()
        print(f"  {week_num}：{week_start}")


def add_schedule_props_to_db1(key: str, db_week_id: str) -> None:
    """DB1 新增 14 個 rich_text schedule props + Current_Week relation"""
    props: dict = {}
    for prefix in ("This", "Next"):
        for day in DAY_LABELS:
            props[f"{prefix}_{day}"] = {"rich_text": {}}
    props["Current_Week"] = {
        "relation": {
            "database_id": db_week_id,
            "single_property": {},
        }
    }
    url = f"https://api.notion.com/v1/databases/{DB_PLAYERS}"
    r = requests.patch(url, headers=notion_headers(key), json={"properties": props})
    r.raise_for_status()
    print(f"  DB1 新增 {len(props)} 個 props 成功")


def update_notion_config(db_week_id: str) -> None:
    config_path = Path(__file__).parent / "notion_config.py"
    content = config_path.read_text()
    new_content = re.sub(
        r'DB_WEEK\s*=\s*""',
        f'DB_WEEK     = "{db_week_id}"',
        content,
    )
    config_path.write_text(new_content)
    print(f"  notion_config.py 已更新：DB_WEEK = \"{db_week_id}\"")


def main():
    key = load_notion_key()

    print("[Step 1] 建立 DB_Week...")
    db_week_id = create_db_week(key)

    print(f"\n[Step 2] 寫入 {TOTAL_WEEKS} 週次...")
    write_weeks(key, db_week_id)

    print(f"\n[Step 3] DB1 新增 14 個 schedule props + Current_Week relation...")
    add_schedule_props_to_db1(key, db_week_id)

    print(f"\n[Step 4] 更新 notion_config.py...")
    update_notion_config(db_week_id)

    print(f"\n完成！DB_WEEK = \"{db_week_id}\"")
    print("下一步：執行 update_schedule.py 填入本週 + 下週賽程")


if __name__ == "__main__":
    main()
