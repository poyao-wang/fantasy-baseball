"""
update_lineup.py — 更新 DB2 今日打線/先發狀態（Lineup_Status）+ DB1 Current_Slot

Lineup_Status（DB2）：
  打者：IN（在打線）/ OUT（有賽不在打線）/ TBD（打線未公布）/ OFF（休息日）
  投手：START（今日先發）/ TBD（有賽但非先發）/ OFF（休息日）

Current_Slot（DB1）：
  從 Yahoo Fantasy API 拉最新陣容，有變動才更新（輪值/換人即時反映）

執行時機：每小時 22:00–08:00 JST（= 13:00–23:00 UTC），RPi cron
"""
import sys
import requests
import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from notion_config import NOTION_KEY_PATH, DB_PLAYERS, DB_SCHEDULE

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


def get_pitcher_names(key: str) -> set[str]:
    """從 DB1 拉所有 Position_Type = P 的球員姓名"""
    url = f"https://api.notion.com/v1/databases/{DB_PLAYERS}/query"
    body: dict = {
        "page_size": 100,
        "filter": {"property": "Position_Type", "select": {"equals": "P"}},
    }
    pitchers: set[str] = set()
    while True:
        r = requests.post(url, headers=notion_headers(key), json=body)
        r.raise_for_status()
        data = r.json()
        for page in data["results"]:
            title_list = page["properties"]["Name"]["title"]
            name = title_list[0]["plain_text"] if title_list else ""
            if name:
                pitchers.add(name)
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return pitchers


def get_today_rows(key: str, today_str: str) -> list[dict]:
    """從 DB2 拉今日所有 rows（排除 OFF），回傳 [{page_id, name, current_status}]"""
    url = f"https://api.notion.com/v1/databases/{DB_SCHEDULE}/query"
    body: dict = {
        "page_size": 100,
        "filter": {
            "and": [
                {"property": "Date", "date": {"equals": today_str}},
                {"property": "Lineup_Status", "select": {"does_not_equal": "OFF"}},
            ]
        },
    }
    rows = []
    while True:
        r = requests.post(url, headers=notion_headers(key), json=body)
        r.raise_for_status()
        data = r.json()
        for page in data["results"]:
            props = page["properties"]
            title_list = props["Title"]["title"]
            name_raw = title_list[0]["plain_text"] if title_list else ""
            name = name_raw.replace(f" {today_str}", "").strip()
            current_status = (props["Lineup_Status"]["select"] or {}).get("name", "TBD")
            if name:
                rows.append({
                    "page_id": page["id"],
                    "name": name,
                    "current_status": current_status,
                })
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return rows


def patch_lineup_status(key: str, page_id: str, status: str) -> None:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    r = requests.patch(
        url,
        headers=notion_headers(key),
        json={"properties": {"Lineup_Status": {"select": {"name": status}}}},
    )
    r.raise_for_status()


def get_db1_slots(key: str) -> dict[int, tuple[str, str]]:
    """從 DB1 拉 My Roster 所有球員，回傳 {player_id: (page_id, current_slot)}"""
    url = f"https://api.notion.com/v1/databases/{DB_PLAYERS}/query"
    body: dict = {
        "page_size": 100,
        "filter": {"property": "Player_Type", "select": {"equals": "My Roster"}},
    }
    result: dict[int, tuple[str, str]] = {}
    while True:
        r = requests.post(url, headers=notion_headers(key), json=body)
        r.raise_for_status()
        data = r.json()
        for page in data["results"]:
            props = page["properties"]
            pid = props["Player_ID"]["number"]
            slot = (props["Current_Slot"]["select"] or {}).get("name", "BN")
            if pid is not None:
                result[int(pid)] = (page["id"], slot)
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return result


def patch_current_slot(key: str, page_id: str, slot: str) -> None:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    r = requests.patch(
        url,
        headers=notion_headers(key),
        json={"properties": {"Current_Slot": {"select": {"name": slot}}}},
    )
    r.raise_for_status()


# ── MLB Stats API ─────────────────────────────────────────────

def get_today_game_data(today_str: str) -> tuple[set[str], set[str], set[str]]:
    """
    查今日所有 MLB 比賽，回傳：
    - in_batting_lineup: set[str]       — 在今日打線的球員姓名
    - probable_starters: set[str]       — 今日先發投手姓名
    - in_published_game_players: set[str] — 已公布打線球隊的全體 roster 球員姓名
      （用於區分 OUT vs TBD：只有自己球隊打線公布了才能判斷 OUT）
    """
    url = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={today_str}&hydrate=probablePitcher,lineups"
    )
    r = requests.get(url)
    r.raise_for_status()

    in_batting_lineup: set[str] = set()
    probable_starters: set[str] = set()
    published_team_ids: set[int] = set()

    for d in r.json().get("dates", []):
        for game in d.get("games", []):
            # 先發投手
            for side in ("home", "away"):
                pitcher = game["teams"][side].get("probablePitcher", {})
                if pitcher.get("fullName"):
                    probable_starters.add(pitcher["fullName"])

            # 打線
            lineups = game.get("lineups", {})
            home_players = [p.get("fullName", "") for p in lineups.get("homePlayers", [])]
            away_players = [p.get("fullName", "") for p in lineups.get("awayPlayers", [])]
            if home_players:
                in_batting_lineup.update(home_players)
                published_team_ids.add(game["teams"]["home"]["team"]["id"])
            if away_players:
                in_batting_lineup.update(away_players)
                published_team_ids.add(game["teams"]["away"]["team"]["id"])

    # 撈已公布打線球隊的完整 roster，才能正確判斷未在打線的球員是 OUT（非 TBD）
    in_published_game_players: set[str] = set(in_batting_lineup)
    for team_id in published_team_ids:
        try:
            tr = requests.get(
                f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active",
                timeout=10,
            )
            tr.raise_for_status()
            for p in tr.json().get("roster", []):
                name = p.get("person", {}).get("fullName", "")
                if name:
                    in_published_game_players.add(name)
        except Exception:
            pass  # 單隊 roster 失敗不影響整體

    return in_batting_lineup, probable_starters, in_published_game_players


# ── 主程式 ────────────────────────────────────────────────────

def main():
    try:
        notion_key = load_notion_key()

        today_et = datetime.now(ZoneInfo("America/New_York")).date()
        today_str = today_et.isoformat()
        now_jst = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%H:%M JST")

        print(f"[update_lineup] {today_str}  執行時間：{now_jst}\n")

        # ── Current_Slot 同步（DB1）────────────────────────────
        print("[Yahoo] 拉取最新陣容...")
        sc = OAuth2(None, None, from_file="oauth2.json")
        if not sc.token_is_valid():
            sc.refresh_access_token()
        league = yfa.Game(sc, "mlb").to_league(LEAGUE_ID)
        roster = league.to_team(league.team_key()).roster()

        yahoo_slots: dict[int, tuple[str, str]] = {}  # {player_id: (name, slot)}
        for p in roster:
            key_str = p.get("player_key", "")
            pid = int(p["player_id"]) if "player_id" in p else int(key_str.split(".")[-1])
            yahoo_slots[pid] = (p["name"], p.get("selected_position", "BN"))
        print(f"  → 陣容 {len(yahoo_slots)} 人\n")

        print("[Notion] 拉取 DB1 Current_Slot...")
        db1_slots = get_db1_slots(notion_key)
        print(f"  → 共 {len(db1_slots)} 筆\n")

        slot_ok, slot_skip, slot_fail = 0, 0, 0
        for pid, (name, new_slot) in yahoo_slots.items():
            if pid not in db1_slots:
                continue
            page_id, old_slot = db1_slots[pid]
            if new_slot == old_slot:
                slot_skip += 1
                continue
            try:
                patch_current_slot(notion_key, page_id, new_slot)
                print(f"  [slot] {name:<28} {old_slot} → {new_slot}")
                slot_ok += 1
            except Exception as e:
                print(f"  [slot錯誤] {name}: {e}")
                slot_fail += 1

        print(f"Current_Slot：{slot_ok} 更新 / {slot_skip} 無變動 / {slot_fail} 失敗\n")
        _append_sync_log(f"[update_lineup] slot {slot_ok} 更新 / {slot_skip} 無變動 / {slot_fail} 失敗")

        # DB1 投手名單
        print("[Notion] 拉取 DB1 投手名單...")
        pitchers = get_pitcher_names(notion_key)
        print(f"  → 共 {len(pitchers)} 位投手\n")

        # DB2 今日 rows
        print("[Notion] 拉取今日 DB2 rows...")
        rows = get_today_rows(notion_key, today_str)
        print(f"  → 共 {len(rows)} 筆（已排除 OFF）\n")

        if not rows:
            print("今日無需更新的 rows，結束。")
            _append_sync_log(f"[update_lineup] 0 更新 / 0 無變動 / 0 失敗（今日無賽）")
            return

        # MLB 今日打線 + 先發
        print("[MLB] 拉取今日打線與先發投手...")
        in_batting_lineup, probable_starters, in_published_game_players = get_today_game_data(today_str)
        print(f"  → 先發投手：{len(probable_starters)} 人  |  已公布打線球隊 roster：{len(in_published_game_players)} 人  |  打線人數：{len(in_batting_lineup)}\n")

        # 更新
        ok, skip, fail = 0, 0, 0
        for row in rows:
            name = row["name"]
            is_pitcher = name in pitchers

            if is_pitcher:
                if name in probable_starters:
                    new_status = "START"
                else:
                    new_status = "TBD"
            else:
                if name in in_batting_lineup:
                    new_status = "IN"
                elif name in in_published_game_players:
                    new_status = "OUT"   # 自己球隊打線已公布但不在其中
                else:
                    new_status = "TBD"  # 自己球隊打線尚未公布

            old_status = row["current_status"]
            if new_status == old_status:
                print(f"  [skip] {name:<28} {old_status}（無變動）")
                skip += 1
                continue

            try:
                patch_lineup_status(notion_key, row["page_id"], new_status)
                tag = "P" if is_pitcher else "B"
                print(f"  [更新/{tag}] {name:<26} {old_status} → {new_status}")
                ok += 1
            except Exception as e:
                print(f"  [錯誤] {name}: {e}")
                fail += 1

        print(f"\n完成：Lineup_Status {ok} 更新 / {skip} 無變動 / {fail} 失敗")
        _append_sync_log(
            f"[update_lineup] Lineup_Status {ok}更新/{skip}無變動/{fail}失敗  "
            f"| Current_Slot {slot_ok}更新/{slot_skip}無變動/{slot_fail}失敗"
        )
    except Exception as e:
        _append_sync_log(f"[update_lineup] ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
