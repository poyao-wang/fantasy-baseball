"""
update_roster.py — 從 Yahoo Fantasy API 拉取我的陣容，upsert 到 Notion DB1 (Players)
upsert key: Player_ID（Yahoo player_id）
Player_Type: My Roster
執行時機：每週一 9am JST / 手動
"""
import sys
import requests
import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# sync/ 的上層就是專案根，把根目錄加入 path 才能 import notion_config
sys.path.insert(0, str(Path(__file__).parent))
from notion_config import NOTION_KEY_PATH, DB_PLAYERS

LEAGUE_ID = "469.l.171948"


# ── sync log ──────────────────────────────────────────────────

def _append_sync_log(message: str) -> None:
    log_path = Path(__file__).parent.parent / "sync.log"
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M JST")
    with open(log_path, "a") as f:
        f.write(f"{now} {message}\n")


# ── Notion helpers ────────────────────────────────────────────

def load_notion_key() -> str:
    return Path(NOTION_KEY_PATH).expanduser().read_text().strip()


def notion_headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }



def fetch_all_my_roster_pages(key: str) -> dict[int, str]:
    """DB1 裡所有 Player_Type == My Roster 的 pages，回傳 {player_id: page_id}"""
    url = f"https://api.notion.com/v1/databases/{DB_PLAYERS}/query"
    body: dict = {
        "page_size": 100,
        "filter": {"property": "Player_Type", "select": {"equals": "My Roster"}},
    }
    result: dict[int, str] = {}
    while True:
        r = requests.post(url, headers=notion_headers(key), json=body)
        r.raise_for_status()
        data = r.json()
        for page in data["results"]:
            pid_prop = page["properties"].get("Player_ID", {}).get("number")
            if pid_prop is not None:
                result[int(pid_prop)] = page["id"]
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return result


def archive_page(key: str, page_id: str) -> None:
    """把 Notion page archive（等同刪除）"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    r = requests.patch(url, headers=notion_headers(key), json={"archived": True})
    r.raise_for_status()


# ── 資料轉換 ──────────────────────────────────────────────────

def extract_player_id(p: dict) -> int:
    """從 player_id 欄位或 player_key（格式：422.p.8967）解析出數字 ID"""
    if "player_id" in p:
        return int(p["player_id"])
    key = p.get("player_key", "")
    return int(key.split(".")[-1])


def normalize_status(p: dict) -> str:
    """Yahoo status + selected_position → Healthy / DTD / IL"""
    slot = p.get("selected_position", "")
    raw = (p.get("status") or "").upper()
    if slot == "IL" or "IL" in raw:
        return "IL"
    if "DTD" in raw:
        return "DTD"
    return "Healthy"


def build_properties(p: dict, player_id: int) -> dict:
    """把 Yahoo roster dict 轉成 Notion properties payload"""
    eligible = [pos for pos in p.get("eligible_positions", []) if pos != "Util"]
    return {
        "Name": {
            "title": [{"text": {"content": p["name"]}}]
        },
        "MLB_Team": {
            "select": {"name": p.get("editorial_team_abbr") or "FA"}
        },
        "Player_Type": {
            "select": {"name": "My Roster"}
        },
        "Current_Slot": {
            "select": {"name": p.get("selected_position", "BN")}
        },
        "Eligible_Positions": {
            "multi_select": [{"name": pos} for pos in eligible]
        },
        "Position_Type": {
            "select": {"name": p.get("position_type", "B")}
        },
        "Status": {
            "select": {"name": normalize_status(p)}
        },
        "Player_ID": {
            "number": player_id
        },
    }


# ── upsert ────────────────────────────────────────────────────

def upsert_player(key: str, p: dict, page_id: str | None) -> str:
    """存在則 PATCH，不存在則 POST。回傳 '更新' 或 '新增'"""
    player_id = extract_player_id(p)
    props = build_properties(p, player_id)

    if page_id:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        r = requests.patch(url, headers=notion_headers(key), json={"properties": props})
    else:
        url = "https://api.notion.com/v1/pages"
        body = {"parent": {"database_id": DB_PLAYERS}, "properties": props}
        r = requests.post(url, headers=notion_headers(key), json=body)

    r.raise_for_status()
    return "更新" if page_id else "新增"


# ── 主程式 ────────────────────────────────────────────────────

def main():
    try:
        notion_key = load_notion_key()

        sc = OAuth2(None, None, from_file="oauth2.json")
        if not sc.token_is_valid():
            sc.refresh_access_token()

        gm = yfa.Game(sc, "mlb")
        league = gm.to_league(LEAGUE_ID)
        my_team = league.to_team(league.team_key())
        roster = my_team.roster()

        print(f"陣容共 {len(roster)} 人，開始 upsert 到 Notion DB1...\n")

        # 一次 batch 拉完 Notion 現有陣容，供 upsert 和清除共用
        print("[Notion] 拉取 DB1 現有陣容（batch）...")
        notion_roster = fetch_all_my_roster_pages(notion_key)
        print(f"  → 共 {len(notion_roster)} 筆\n")

        ok, fail = 0, 0
        for p in roster:
            try:
                pid = extract_player_id(p)
                action = upsert_player(notion_key, p, notion_roster.get(pid))
                slot = p.get("selected_position", "?")
                pos_type = p.get("position_type", "?")
                status = normalize_status(p)
                flag = f" ⚠ {p['status']}" if p.get("status") else ""
                print(f"  [{action}] {p['name']:<28} {pos_type} [{slot}] {status}{flag}")
                ok += 1
            except Exception as e:
                print(f"  [錯誤] {p.get('name', '?')}: {e}")
                fail += 1

        # ── 清除已離隊球員 ────────────────────────────────────────
        current_ids = {extract_player_id(p) for p in roster}
        stale = {pid: pid_page for pid, pid_page in notion_roster.items() if pid not in current_ids}

        removed = 0
        for pid, pid_page in stale.items():
            try:
                archive_page(notion_key, pid_page)
                print(f"  [移除] player_id={pid}（已不在陣容）")
                removed += 1
            except Exception as e:
                print(f"  [錯誤] archive player_id={pid}: {e}")

        if removed:
            print(f"\n  共移除 {removed} 位已離隊球員")

        print(f"\n完成：{ok} 成功 / {fail} 失敗 / {removed} 移除  →  Notion DB1 Players")
        _append_sync_log(f"[update_roster] {ok} 成功 / {fail} 失敗 / {removed} 移除")
    except Exception as e:
        _append_sync_log(f"[update_roster] ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
