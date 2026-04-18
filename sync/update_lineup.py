"""
update_lineup.py — 更新 DB1 Today_Status + Current_Slot

Today_Status（DB1）：
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


def get_db1_my_roster(key: str) -> dict[int, dict]:
    """
    DB1 My Roster 全量（一次查詢）。
    回傳 {player_id: {page_id, name, current_slot, today_status, position_type, mlb_team}}
    """
    url = f"https://api.notion.com/v1/databases/{DB_PLAYERS}/query"
    body: dict = {
        "page_size": 100,
        "filter": {"property": "Player_Type", "select": {"equals": "My Roster"}},
    }
    result: dict[int, dict] = {}
    while True:
        r = requests.post(url, headers=notion_headers(key), json=body)
        r.raise_for_status()
        data = r.json()
        for page in data["results"]:
            props = page["properties"]
            pid = props["Player_ID"]["number"]
            if pid is None:
                continue
            pid = int(pid)
            name_list = props["Name"]["title"]
            name = name_list[0]["plain_text"] if name_list else ""
            if not name:
                continue
            result[pid] = {
                "page_id": page["id"],
                "name": name,
                "current_slot": (props["Current_Slot"]["select"] or {}).get("name", "BN"),
                "today_status": (props.get("Today_Status", {}).get("select") or {}).get("name", "TBD"),
                "position_type": (props.get("Position_Type", {}).get("select") or {}).get("name", "B"),
                "mlb_team": (props.get("MLB_Team", {}).get("select") or {}).get("name", ""),
            }
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


def patch_today_status(key: str, page_id: str, status: str) -> None:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    r = requests.patch(
        url,
        headers=notion_headers(key),
        json={"properties": {"Today_Status": {"select": {"name": status}}}},
    )
    r.raise_for_status()


# ── MLB Stats API ─────────────────────────────────────────────

def get_today_game_data(today_str: str) -> tuple[set[str], set[str], set[str], set[str]]:
    """
    查今日所有 MLB 比賽，回傳：
    - in_batting_lineup: set[str]         — 在今日打線的球員姓名
    - probable_starters: set[str]         — 今日先發投手姓名
    - in_published_game_players: set[str] — 已公布打線球隊的全體 roster 球員姓名
    - playing_team_abbrevs: set[str]      — 今日有賽球隊縮寫（如 TOR, LAD）
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
    playing_team_abbrevs: set[str] = set()

    for d in r.json().get("dates", []):
        for game in d.get("games", []):
            for side in ("home", "away"):
                team = game["teams"][side]
                abbrev = team["team"].get("abbreviation", "")
                if abbrev:
                    playing_team_abbrevs.add(abbrev)
                pitcher = team.get("probablePitcher", {})
                if pitcher.get("fullName"):
                    probable_starters.add(pitcher["fullName"])

            lineups = game.get("lineups", {})
            home_players = [p.get("fullName", "") for p in lineups.get("homePlayers", [])]
            away_players = [p.get("fullName", "") for p in lineups.get("awayPlayers", [])]
            if home_players:
                in_batting_lineup.update(home_players)
                published_team_ids.add(game["teams"]["home"]["team"]["id"])
            if away_players:
                in_batting_lineup.update(away_players)
                published_team_ids.add(game["teams"]["away"]["team"]["id"])

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
            pass

    return in_batting_lineup, probable_starters, in_published_game_players, playing_team_abbrevs


# ── 主程式 ────────────────────────────────────────────────────

def main():
    try:
        notion_key = load_notion_key()

        today_et = datetime.now(ZoneInfo("America/New_York")).date()
        today_str = today_et.isoformat()
        now_jst = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%H:%M JST")

        print(f"[update_lineup] {today_str}  執行時間：{now_jst}\n")

        # ── DB1 全量查詢（一次） ───────────────────────────────
        print("[Notion] 拉取 DB1 My Roster...")
        players = get_db1_my_roster(notion_key)
        print(f"  → 共 {len(players)} 筆\n")

        # ── Current_Slot 同步（DB1）────────────────────────────
        print("[Yahoo] 拉取最新陣容...")
        sc = OAuth2(None, None, from_file="oauth2.json")
        if not sc.token_is_valid():
            sc.refresh_access_token()
        for _attempt in range(2):
            try:
                league = yfa.Game(sc, "mlb").to_league(LEAGUE_ID)
                roster = league.to_team(league.team_key()).roster()
                break
            except Exception as e:
                if _attempt == 0 and ("Forbidden" in str(e) or "401" in str(e) or "403" in str(e)):
                    print(f"  [Yahoo] token 疑似過期，強制 refresh 後 retry... ({e})")
                    sc.refresh_access_token()
                else:
                    raise

        yahoo_slots: dict[int, tuple[str, str]] = {}
        for p in roster:
            key_str = p.get("player_key", "")
            pid = int(p["player_id"]) if "player_id" in p else int(key_str.split(".")[-1])
            yahoo_slots[pid] = (p["name"], p.get("selected_position", "BN"))
        print(f"  → 陣容 {len(yahoo_slots)} 人\n")

        slot_ok, slot_skip, slot_fail = 0, 0, 0
        for pid, (name, new_slot) in yahoo_slots.items():
            if pid not in players:
                continue
            info = players[pid]
            if new_slot == info["current_slot"]:
                slot_skip += 1
                continue
            try:
                patch_current_slot(notion_key, info["page_id"], new_slot)
                print(f"  [slot] {name:<28} {info['current_slot']} → {new_slot}")
                info["current_slot"] = new_slot  # 更新本地快取
                slot_ok += 1
            except Exception as e:
                print(f"  [slot錯誤] {name}: {e}")
                slot_fail += 1

        print(f"Current_Slot：{slot_ok} 更新 / {slot_skip} 無變動 / {slot_fail} 失敗\n")
        _append_sync_log(f"[update_lineup] slot {slot_ok} 更新 / {slot_skip} 無變動 / {slot_fail} 失敗")

        # ── Today_Status 更新（DB1）────────────────────────────
        print("[MLB] 拉取今日打線與先發投手...")
        in_batting_lineup, probable_starters, in_published_game_players, playing_team_abbrevs = get_today_game_data(today_str)
        print(f"  → 今日出賽球隊：{len(playing_team_abbrevs)} 隊  |  先發投手：{len(probable_starters)} 人  |  打線人數：{len(in_batting_lineup)}\n")

        ok, skip, fail = 0, 0, 0
        for pid, info in players.items():
            name = info["name"]
            mlb_team = info["mlb_team"]
            is_pitcher = info["position_type"] == "P"

            if mlb_team not in playing_team_abbrevs:
                new_status = "OFF"
            elif is_pitcher:
                new_status = "START" if name in probable_starters else "TBD"
            elif name in in_batting_lineup:
                new_status = "IN"
            elif name in in_published_game_players:
                new_status = "OUT"
            else:
                new_status = "TBD"

            old_status = info["today_status"]
            if new_status == old_status:
                skip += 1
                continue

            try:
                patch_today_status(notion_key, info["page_id"], new_status)
                tag = "P" if is_pitcher else "B"
                print(f"  [更新/{tag}] {name:<26} {old_status} → {new_status}")
                ok += 1
            except Exception as e:
                print(f"  [錯誤] {name}: {e}")
                fail += 1

        print(f"\n完成：Today_Status {ok} 更新 / {skip} 無變動 / {fail} 失敗")
        _append_sync_log(
            f"[update_lineup] Today_Status {ok}更新/{skip}無變動/{fail}失敗  "
            f"| Current_Slot {slot_ok}更新/{slot_skip}無變動/{slot_fail}失敗"
        )
    except Exception as e:
        _append_sync_log(f"[update_lineup] ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
