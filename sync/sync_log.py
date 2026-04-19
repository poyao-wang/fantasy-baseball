"""
sync_log.py — 把 sync.log 新增行同步到 Notion DB4 Logs

cursor 機制：sync.log.cursor 記錄上次已同步的行數，每次只處理新行。
每筆格式：YYYY-MM-DD HH:MM JST [script] message
"""
import re
import sys
import time
import requests
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from notion_config import NOTION_KEY_PATH, DB_LOGS

LOG_FILE    = Path(__file__).parent.parent / "sync.log"
CURSOR_FILE = Path(__file__).parent.parent / "sync.log.cursor"
JST = ZoneInfo("Asia/Tokyo")

LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}) JST \[(?P<script>[^\]]+)\] (?P<msg>.+)$"
)
KNOWN_SCRIPTS = {
    "update_roster", "update_schedule", "update_stats",
    "update_lineup", "auto_swap", "add_trade_target",
}


def load_notion_key() -> str:
    return Path(NOTION_KEY_PATH).expanduser().read_text().strip()


def notion_headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def load_cursor() -> int:
    if CURSOR_FILE.exists():
        try:
            return int(CURSOR_FILE.read_text().strip())
        except ValueError:
            return 0
    return 0


def save_cursor(n: int) -> None:
    CURSOR_FILE.write_text(str(n))


def parse_new_lines(cursor: int) -> tuple[list[dict], int]:
    """從 cursor 行之後讀取新行，回傳 (entries, total_line_count)"""
    if not LOG_FILE.exists():
        return [], 0
    all_lines = LOG_FILE.read_text().splitlines()
    total = len(all_lines)
    entries = []
    for raw in all_lines[cursor:]:
        line = raw.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        script = m.group("script")
        if script not in KNOWN_SCRIPTS:
            continue
        ts_str  = m.group("ts")
        message = m.group("msg")
        title   = f"{ts_str} JST [{script}]"
        status  = "ERROR" if "ERROR" in message else "OK"
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        entries.append({
            "title":     title,
            "script":    script,
            "message":   message,
            "status":    status,
            "logged_at": dt.isoformat(),
        })
    return entries, total


def notion_request(method: str, url: str, headers: dict, **kwargs) -> requests.Response:
    """帶 429 retry 的 Notion API 請求（最多 3 次，指數退避）"""
    for attempt in range(3):
        r = getattr(requests, method)(url, headers=headers, **kwargs)
        if r.status_code == 429:
            wait = 2 ** attempt * 5  # 5s, 10s, 20s
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def create_entry(key: str, entry: dict) -> None:
    props = {
        "Title":     {"title": [{"text": {"content": entry["title"]}}]},
        "Script":    {"select": {"name": entry["script"]}},
        "Message":   {"rich_text": [{"text": {"content": entry["message"][:2000]}}]},
        "Status":    {"select": {"name": entry["status"]}},
        "Logged_At": {"date": {"start": entry["logged_at"]}},
    }
    notion_request("post", "https://api.notion.com/v1/pages",
                   notion_headers(key),
                   json={"parent": {"database_id": DB_LOGS}, "properties": props})


def main():
    key    = load_notion_key()
    cursor = load_cursor()
    entries, total_lines = parse_new_lines(cursor)

    if not entries:
        print(f"[sync_log] 無新增 log（已同步至第 {cursor} 行）")
        save_cursor(total_lines)
        return

    print(f"[sync_log] 新增 {len(entries)} 筆（從第 {cursor} 行起），同步到 Notion DB4...\n")
    added, failed = 0, 0

    for entry in entries:
        try:
            create_entry(key, entry)
            print(f"  [新增] {entry['title']}  {entry['status']}  {entry['message'][:60]}")
            added += 1
        except Exception as e:
            print(f"  [錯誤] {entry['title']}: {e}")
            failed += 1

    save_cursor(total_lines)
    print(f"\n完成：{added} 新增 / {failed} 失敗  →  Notion DB4 Logs")


if __name__ == "__main__":
    main()
