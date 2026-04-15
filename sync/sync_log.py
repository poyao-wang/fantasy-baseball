"""
sync_log.py — 把 sync.log 同步到 Notion DB4 Logs

每行格式：YYYY-MM-DD HH:MM JST [script] message
- Title（upsert key）：「YYYY-MM-DD HH:MM JST [script]」
- Script：update_roster / update_schedule / update_stats / update_lineup / auto_swap
- Message：剩餘內容
- Status：ERROR（含「ERROR」）/ OK
- Logged_At：ISO 8601 datetime（JST）

執行時機：每次 cron job 結束後（接在 update_lineup / auto_swap / 週一全量之後）
"""
import re
import sys
import requests
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from notion_config import NOTION_KEY_PATH, DB_LOGS

LOG_FILE = Path(__file__).parent.parent / "sync.log"
JST = ZoneInfo("Asia/Tokyo")

# sync.log 每行格式：2026-04-14 07:19 JST [update_lineup] ...
LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}) JST \[(?P<script>[^\]]+)\] (?P<msg>.+)$"
)

KNOWN_SCRIPTS = {
    "update_roster", "update_schedule", "update_stats",
    "update_lineup", "auto_swap",
}


def load_notion_key() -> str:
    return Path(NOTION_KEY_PATH).expanduser().read_text().strip()


def notion_headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def parse_log_lines() -> list[dict]:
    """讀取 sync.log，回傳 list of {title, script, message, status, logged_at}"""
    if not LOG_FILE.exists():
        return []
    entries = []
    for raw in LOG_FILE.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        ts_str  = m.group("ts")          # "2026-04-14 07:19"
        script  = m.group("script")
        message = m.group("msg")

        if script not in KNOWN_SCRIPTS:
            continue

        title   = f"{ts_str} JST [{script}]"
        status  = "ERROR" if "ERROR" in message else "OK"

        # 轉成 ISO 8601（JST offset +09:00）給 Notion date
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        logged_at = dt.isoformat()

        entries.append({
            "title":     title,
            "script":    script,
            "message":   message,
            "status":    status,
            "logged_at": logged_at,
        })
    return entries


def find_page_by_title(key: str, title: str) -> str | None:
    """DB4 裡找 Title == title 的 page_id，沒有回 None"""
    url = f"https://api.notion.com/v1/databases/{DB_LOGS}/query"
    body = {"filter": {"property": "Title", "title": {"equals": title}}}
    r = requests.post(url, headers=notion_headers(key), json=body)
    r.raise_for_status()
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


def build_properties(entry: dict) -> dict:
    return {
        "Title": {
            "title": [{"text": {"content": entry["title"]}}]
        },
        "Script": {
            "select": {"name": entry["script"]}
        },
        "Message": {
            "rich_text": [{"text": {"content": entry["message"][:2000]}}]
        },
        "Status": {
            "select": {"name": entry["status"]}
        },
        "Logged_At": {
            "date": {"start": entry["logged_at"]}
        },
    }


def upsert_entry(key: str, entry: dict) -> str:
    """存在則更新 message/status，不存在則新增。回傳 '新增'、'更新' 或 '略過'"""
    page_id = find_page_by_title(key, entry["title"])
    if page_id:
        # 用 PATCH 更新 message 與 status，確保 Notion 永遠顯示最新內容
        props = {
            "Message": {"rich_text": [{"text": {"content": entry["message"][:2000]}}]},
            "Status":  {"select": {"name": entry["status"]}},
        }
        url = f"https://api.notion.com/v1/pages/{page_id}"
        r = requests.patch(url, headers=notion_headers(key), json={"properties": props})
        r.raise_for_status()
        return "更新"
    props = build_properties(entry)
    url = "https://api.notion.com/v1/pages"
    body = {"parent": {"database_id": DB_LOGS}, "properties": props}
    r = requests.post(url, headers=notion_headers(key), json=body)
    r.raise_for_status()
    return "新增"


def main():
    key = load_notion_key()
    entries = parse_log_lines()

    if not entries:
        print("[sync_log] sync.log 無有效資料")
        return

    print(f"[sync_log] 讀到 {len(entries)} 筆 log，開始同步到 Notion DB4...\n")
    added, updated, skipped, failed = 0, 0, 0, 0

    for entry in entries:
        try:
            action = upsert_entry(key, entry)
            if action != "略過":
                print(f"  [{action}] {entry['title']}  {entry['status']}  {entry['message'][:60]}")
            if action == "新增":
                added += 1
            elif action == "更新":
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  [錯誤] {entry['title']}: {e}")
            failed += 1

    print(f"\n完成：{added} 新增 / {updated} 更新 / {skipped} 略過 / {failed} 失敗  →  Notion DB4 Logs")


if __name__ == "__main__":
    main()
