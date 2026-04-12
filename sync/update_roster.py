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
from pathlib import Path

# sync/ 的上層就是專案根，把根目錄加入 path 才能 import notion_config
sys.path.insert(0, str(Path(__file__).parent))
from notion_config import NOTION_KEY_PATH, DB_PLAYERS

LEAGUE_ID = "469.l.171948"


# ── Notion helpers ────────────────────────────────────────────

def load_notion_key() -> str:
    return Path(NOTION_KEY_PATH).expanduser().read_text().strip()


def notion_headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def find_page_by_player_id(key: str, player_id: int) -> str | None:
    """DB1 裡找 Player_ID == player_id 的 page，回傳 page_id 或 None"""
    url = f"https://api.notion.com/v1/databases/{DB_PLAYERS}/query"
    body = {"filter": {"property": "Player_ID", "number": {"equals": player_id}}}
    r = requests.post(url, headers=notion_headers(key), json=body)
    r.raise_for_status()
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


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

def upsert_player(key: str, p: dict) -> str:
    """存在則 PATCH，不存在則 POST。回傳 '更新' 或 '新增'"""
    player_id = extract_player_id(p)
    props = build_properties(p, player_id)
    page_id = find_page_by_player_id(key, player_id)

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
    notion_key = load_notion_key()

    sc = OAuth2(None, None, from_file="oauth2.json")
    if not sc.token_is_valid():
        sc.refresh_access_token()

    gm = yfa.Game(sc, "mlb")
    league = gm.to_league(LEAGUE_ID)
    my_team = league.to_team(league.team_key())
    roster = my_team.roster()

    print(f"陣容共 {len(roster)} 人，開始 upsert 到 Notion DB1...\n")

    ok, fail = 0, 0
    for p in roster:
        try:
            action = upsert_player(notion_key, p)
            slot = p.get("selected_position", "?")
            pos_type = p.get("position_type", "?")
            status = normalize_status(p)
            flag = f" ⚠ {p['status']}" if p.get("status") else ""
            print(f"  [{action}] {p['name']:<28} {pos_type} [{slot}] {status}{flag}")
            ok += 1
        except Exception as e:
            print(f"  [錯誤] {p.get('name', '?')}: {e}")
            fail += 1

    print(f"\n完成：{ok} 成功 / {fail} 失敗  →  Notion DB1 Players")


if __name__ == "__main__":
    main()
