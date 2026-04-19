"""
update_schedule.py — 更新 DB1 所有球員的兩週賽程 props（This_Mon～Next_Sun）+ Current_Week relation
執行時機：每週一 9am JST

prop 格式：
  野手有賽：「vs NYY / Gausman」（對手 / opposing SP，SP 未確認則只顯示 vs NYY）
  野手 OFF：空字串
  投手確認先發：「vs NYY」（bold rich_text）
  投手有賽未確認：「vs NYY」（plain）
  投手 OFF：空字串
"""
import sys
import argparse
import requests
import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2
from datetime import date, timedelta, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from notion_config import NOTION_KEY_PATH, DB_PLAYERS, DB_WEEK

LEAGUE_ID = "469.l.171948"
DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


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


def get_all_players(key: str) -> list[dict]:
    """DB1 所有球員（My Roster + Trade Target）"""
    url = f"https://api.notion.com/v1/databases/{DB_PLAYERS}/query"
    players = []
    body: dict = {"page_size": 100}
    while True:
        r = requests.post(url, headers=notion_headers(key), json=body)
        r.raise_for_status()
        data = r.json()
        for page in data["results"]:
            props = page["properties"]
            name_list = props["Name"]["title"]
            name = name_list[0]["plain_text"] if name_list else ""
            if not name:
                continue
            players.append({
                "name":          name,
                "page_id":       page["id"],
                "mlb_team":      (props["MLB_Team"]["select"] or {}).get("name", ""),
                "position_type": (props["Position_Type"]["select"] or {}).get("name", "B"),
            })
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return players


def get_current_week_page_id(key: str, week_start: date) -> str | None:
    if not DB_WEEK:
        return None
    url = f"https://api.notion.com/v1/databases/{DB_WEEK}/query"
    body = {"filter": {"property": "Week_Start", "date": {"equals": week_start.isoformat()}}}
    r = requests.post(url, headers=notion_headers(key), json=body)
    r.raise_for_status()
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


# ── MLB Stats API ─────────────────────────────────────────────

def get_mlb_team_ids() -> tuple[dict, dict]:
    r = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1")
    r.raise_for_status()
    abbr_to_id = {t["abbreviation"]: t["id"] for t in r.json()["teams"]}
    id_to_abbr = {t["id"]: t["abbreviation"] for t in r.json()["teams"]}
    return abbr_to_id, id_to_abbr


def get_team_schedule_range(team_id: int, start: date, end: date, id_to_abbr: dict) -> dict[str, dict]:
    """
    回傳 {date_str: {matchup, opp_pitcher, our_pitcher, lineup}}
    opp_pitcher / our_pitcher：未確認時為空字串
    """
    url = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&teamId={team_id}"
        f"&startDate={start}&endDate={end}"
        f"&hydrate=probablePitcher,lineups"
    )
    r = requests.get(url)
    r.raise_for_status()
    result: dict[str, dict] = {}
    for d in r.json().get("dates", []):
        for game in d.get("games", []):
            home = game["teams"]["home"]
            away = game["teams"]["away"]
            is_home = home["team"]["id"] == team_id
            opp_id   = away["team"]["id"] if is_home else home["team"]["id"]
            opp_team = id_to_abbr.get(opp_id, "???")
            side = "vs" if is_home else "@"
            our_side = home if is_home else away
            opp_side = away if is_home else home
            opp_pitcher = opp_side.get("probablePitcher", {}).get("fullName", "")
            our_pitcher = our_side.get("probablePitcher", {}).get("fullName", "")
            lineups    = game.get("lineups", {})
            lineup_key = "homePlayers" if is_home else "awayPlayers"
            lineup_names = [p.get("fullName", "") for p in lineups.get(lineup_key, [])]
            result[d["date"]] = {
                "matchup":     f"{side} {opp_team}",
                "opp_pitcher": opp_pitcher,
                "our_pitcher": our_pitcher,
                "lineup":      lineup_names,
            }
    return result


# ── schedule prop builders ────────────────────────────────────

def build_day_value(player_name: str, position_type: str, game_info: dict | None) -> tuple[str, bool]:
    """回傳 (text, is_bold)"""
    if game_info is None:
        return "", False
    matchup = game_info["matchup"]
    if position_type == "P":
        our_pitcher = game_info.get("our_pitcher", "")
        is_confirmed = bool(our_pitcher) and our_pitcher == player_name
        return matchup, is_confirmed
    else:
        opp = game_info.get("opp_pitcher", "")
        if opp:
            return f"{matchup} / {opp}", False
        return matchup, False


def make_rich_text(text: str, bold: bool = False) -> dict:
    if not text:
        return {"rich_text": []}
    item: dict = {"text": {"content": text}}
    if bold:
        item["annotations"] = {"bold": True}
    return {"rich_text": [item]}


def build_schedule_props(player: dict, schedule: dict, this_monday: date, next_monday: date) -> dict:
    props = {}
    for prefix, week_start in [("This", this_monday), ("Next", next_monday)]:
        for i, day_name in enumerate(DAY_LABELS):
            date_str = (week_start + timedelta(days=i)).isoformat()
            game_info = schedule.get(date_str)
            text, bold = build_day_value(player["name"], player["position_type"], game_info)
            props[f"{prefix}_{day_name}"] = make_rich_text(text, bold)
    return props


# ── 主程式 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只印輸出，不寫入 Notion")
    args = parser.parse_args()

    try:
        notion_key = load_notion_key()

        today_et = datetime.now(ZoneInfo("America/New_York")).date()
        days_since_monday = today_et.weekday()
        this_monday = today_et - timedelta(days=days_since_monday)
        next_monday = this_monday + timedelta(days=7)
        next_sunday = next_monday + timedelta(days=6)

        print(f"[update_schedule] {'[DRY-RUN] ' if args.dry_run else ''}今日 ET：{today_et}")
        print(f"  本週：{this_monday} ～ {this_monday + timedelta(days=6)}")
        print(f"  下週：{next_monday} ～ {next_sunday}\n")

        # DB1 球員清單
        print("[Notion] 拉取 DB1 球員清單...")
        players = get_all_players(notion_key)
        print(f"  → 共 {len(players)} 人\n")

        # MLB team IDs
        print("[MLB] 拉取球隊 ID 對照表...")
        abbr_to_id, id_to_abbr = get_mlb_team_ids()

        # 本週 Current_Week page ID
        week_page_id: str | None = None
        if DB_WEEK:
            print("[Notion] 查詢本週 DB_Week page ID...")
            week_page_id = get_current_week_page_id(notion_key, this_monday)
            if week_page_id:
                print(f"  → 找到：{week_page_id}")
            else:
                print(f"  → 找不到 {this_monday}，Current_Week 將略過")
        else:
            print("[略過] DB_WEEK 未設定，Current_Week relation 不更新")
        print()

        # 每支球隊的 14 天賽程（只打一次 API）
        unique_teams = {p["mlb_team"] for p in players if p["mlb_team"] and p["mlb_team"] != "FA"}
        schedule_by_team: dict[str, dict] = {}
        print(f"[MLB] 拉取 {len(unique_teams)} 支球隊兩週賽程（{this_monday} ～ {next_sunday}）...")
        for abbr in sorted(unique_teams):
            team_id = abbr_to_id.get(abbr)
            if team_id:
                schedule_by_team[abbr] = get_team_schedule_range(team_id, this_monday, next_sunday, id_to_abbr)
        print()

        ok, fail = 0, 0
        for player in players:
            sched = schedule_by_team.get(player["mlb_team"], {})
            props = build_schedule_props(player, sched, this_monday, next_monday)

            # 印出摘要
            this_week_summary = " ".join(
                props[f"This_{d}"]["rich_text"][0]["text"]["content"][:6] if props[f"This_{d}"]["rich_text"] else "OFF"
                for d in DAY_LABELS
            )
            print(f"  {player['name']:<28} {this_week_summary}")

            if args.dry_run:
                ok += 1
                continue

            if week_page_id:
                props["Current_Week"] = {"relation": [{"id": week_page_id}]}

            try:
                url = f"https://api.notion.com/v1/pages/{player['page_id']}"
                r = requests.patch(url, headers=notion_headers(notion_key), json={"properties": props})
                r.raise_for_status()
                ok += 1
            except Exception as e:
                print(f"    [錯誤] {player['name']}: {e}")
                fail += 1

        label = "[DRY-RUN] " if args.dry_run else ""
        print(f"\n{label}完成：{ok} 成功 / {fail} 失敗  →  Notion DB1 schedule props")
        if not args.dry_run:
            _append_sync_log(f"[update_schedule] {ok} 成功 / {fail} 失敗")
    except Exception as e:
        _append_sync_log(f"[update_schedule] ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
