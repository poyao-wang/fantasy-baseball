"""
update_schedule.py — 從 DB1 Players 拉球員清單，建立當週 DB2 Schedule rows
upsert key: Title（姓名 YYYY-MM-DD）
Lineup_Status 規則：
  - 過去日期：查實際打線 → IN / OUT（投手一律 TBD，batting lineup 沒有投手）
  - 今天：同上，打線未公布則 TBD
  - 未來日期：TBD
  - 休息日：OFF
執行時機：每週一 9am JST / 手動
"""
import sys
import requests
import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2
from datetime import date, timedelta, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from notion_config import NOTION_KEY_PATH, DB_PLAYERS, DB_SCHEDULE

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


def get_all_players(key: str) -> list[dict]:
    """從 DB1 拉所有球員，回傳 [{name, page_id, mlb_team, player_type}, ...]"""
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
            mlb_team = (props["MLB_Team"]["select"] or {}).get("name", "")
            player_type = (props["Player_Type"]["select"] or {}).get("name", "My Roster")
            position_type = (props["Position_Type"]["select"] or {}).get("name", "B")
            if name:
                players.append({
                    "name": name,
                    "page_id": page["id"],
                    "mlb_team": mlb_team,
                    "player_type": player_type,
                    "position_type": position_type,
                })
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return players


def get_existing_schedule_titles(key: str, week_start: date, week_end: date) -> dict[str, str]:
    """
    拉 DB2 裡本週所有 row（依 Date filter），回傳 {title: page_id}
    用來批次比對，避免每筆都打一次 query API
    """
    url = f"https://api.notion.com/v1/databases/{DB_SCHEDULE}/query"
    body: dict = {
        "page_size": 100,
        "filter": {
            "and": [
                {"property": "Date", "date": {"on_or_after": week_start.isoformat()}},
                {"property": "Date", "date": {"on_or_before": week_end.isoformat()}},
            ]
        },
    }
    existing: dict[str, str] = {}
    while True:
        r = requests.post(url, headers=notion_headers(key), json=body)
        r.raise_for_status()
        data = r.json()
        for page in data["results"]:
            title_list = page["properties"]["Title"]["title"]
            title = title_list[0]["plain_text"] if title_list else ""
            if title:
                existing[title] = page["id"]
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return existing


# ── MLB Stats API ─────────────────────────────────────────────

def get_mlb_team_ids() -> tuple[dict, dict]:
    r = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1")
    abbr_to_id = {t["abbreviation"]: t["id"] for t in r.json()["teams"]}
    id_to_abbr = {t["id"]: t["abbreviation"] for t in r.json()["teams"]}
    return abbr_to_id, id_to_abbr


def get_team_schedule(team_id: int, start: date, end: date, id_to_abbr: dict) -> dict[str, dict]:
    """
    回傳 {date_str: {matchup, pitcher, lineup: [fullName, ...]}}
    只有有比賽的日期才有 key（休息日不在其中）
    lineup 為空 list 表示打線尚未公布
    """
    url = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&teamId={team_id}"
        f"&startDate={start}&endDate={end}"
        f"&hydrate=probablePitcher,lineups"
    )
    r = requests.get(url)
    result: dict[str, dict] = {}
    for d in r.json().get("dates", []):
        for game in d.get("games", []):
            home = game["teams"]["home"]
            away = game["teams"]["away"]
            is_home = home["team"]["id"] == team_id
            opp_id = away["team"]["id"] if is_home else home["team"]["id"]
            opp_team = id_to_abbr.get(opp_id, "???")
            side = "vs" if is_home else "@"
            opp_pitcher = (
                away.get("probablePitcher", {}).get("fullName", "TBD")
                if is_home
                else home.get("probablePitcher", {}).get("fullName", "TBD")
            )
            lineups = game.get("lineups", {})
            lineup_key = "homePlayers" if is_home else "awayPlayers"
            lineup_names = [p.get("fullName", "") for p in lineups.get(lineup_key, [])]
            result[d["date"]] = {
                "matchup": f"{side} {opp_team}",
                "pitcher": opp_pitcher,
                "lineup": lineup_names,
            }
    return result


def determine_lineup_status(
    player_name: str,
    position_type: str,
    day: date,
    today: date,
    game_info: dict | None,
) -> str:
    """決定 Lineup_Status"""
    if game_info is None:
        return "OFF"
    if position_type == "P":
        return "TBD"  # 投手不在 batting lineup，由 update_lineup.py 另行處理
    if day > today:
        return "TBD"  # 未來比賽，打線未定
    lineup = game_info.get("lineup", [])
    if not lineup:
        return "TBD"  # 打線尚未公布（當天比賽但名單還沒出）
    return "IN" if player_name in lineup else "OUT"


# ── upsert ────────────────────────────────────────────────────

def build_schedule_props(
    player: dict,
    day: date,
    today: date,
    game_info: dict | None,
    week: int,
) -> dict:
    title = f"{player['name']} {day.isoformat()}"
    lineup_status = determine_lineup_status(
        player["name"], player["position_type"], day, today, game_info
    )
    opponent = game_info["matchup"] if game_info else ""
    opposing_sp = game_info["pitcher"] if game_info else ""

    return {
        "Title": {"title": [{"text": {"content": title}}]},
        "Player": {"relation": [{"id": player["page_id"]}]},
        "Date": {"date": {"start": day.isoformat()}},
        "Opponent": {"rich_text": [{"text": {"content": opponent}}]},
        "Opposing_SP": {"rich_text": [{"text": {"content": opposing_sp}}]},
        "Lineup_Status": {"select": {"name": lineup_status}},
        "Week": {"number": week},
    }


def upsert_schedule_row(
    key: str,
    player: dict,
    day: date,
    today: date,
    game_info: dict | None,
    week: int,
    existing: dict[str, str],
) -> tuple[str, str]:
    """存在則 PATCH，不存在則 POST。回傳 ('更新'/'新增', lineup_status)"""
    title = f"{player['name']} {day.isoformat()}"
    props = build_schedule_props(player, day, today, game_info, week)
    lineup_status = props["Lineup_Status"]["select"]["name"]
    page_id = existing.get(title)

    if page_id:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        r = requests.patch(url, headers=notion_headers(key), json={"properties": props})
    else:
        url = "https://api.notion.com/v1/pages"
        body = {"parent": {"database_id": DB_SCHEDULE}, "properties": props}
        r = requests.post(url, headers=notion_headers(key), json=body)

    r.raise_for_status()
    return ("更新" if page_id else "新增"), lineup_status


# ── 主程式 ────────────────────────────────────────────────────

def main():
    notion_key = load_notion_key()

    # 日期基準：美東時間（ET）
    today_et = datetime.now(ZoneInfo("America/New_York")).date()

    # Yahoo API：取當前週次
    sc = OAuth2(None, None, from_file="oauth2.json")
    if not sc.token_is_valid():
        sc.refresh_access_token()
    gm = yfa.Game(sc, "mlb")
    league = gm.to_league(LEAGUE_ID)
    week = league.current_week()

    # Fantasy 週次日期：start_date + (week - 1) * 7
    # league_info.json: start_date = 2026-03-25, start_week = 1
    season_start = date(2026, 3, 25)
    week_start = season_start + timedelta(weeks=week - 1)
    week_end = week_start + timedelta(days=6)

    print(f"Fantasy Week {week}：{week_start} ～ {week_end}（ET）")
    print(f"今日 ET：{today_et}\n")

    # MLB team ID map
    print("[MLB] 拉取球隊 ID 對照表...")
    abbr_to_id, id_to_abbr = get_mlb_team_ids()

    # DB1 球員清單
    print("[Notion] 拉取 DB1 球員清單...")
    players = get_all_players(notion_key)
    print(f"  → 共 {len(players)} 人（My Roster + Trade Target）\n")

    # 預先拉本週已存在的 DB2 rows（batch query，減少 API 呼叫）
    print("[Notion] 拉取 DB2 本週已存在的 rows...")
    existing = get_existing_schedule_titles(notion_key, week_start, week_end)
    print(f"  → 本週已存在 {len(existing)} 筆\n")

    # 每支 MLB 球隊的賽程（去重，只打一次 API）
    unique_teams = {p["mlb_team"] for p in players if p["mlb_team"] and p["mlb_team"] != "FA"}
    schedule_by_team: dict[int, dict] = {}
    print(f"[MLB] 拉取 {len(unique_teams)} 支球隊賽程...")
    for abbr in sorted(unique_teams):
        team_id = abbr_to_id.get(abbr)
        if team_id:
            schedule_by_team[team_id] = get_team_schedule(team_id, week_start, week_end, id_to_abbr)
    print()

    # upsert 每球員 × 每天
    days = [week_start + timedelta(days=i) for i in range(7)]
    ok, fail = 0, 0

    for player in players:
        team_id = abbr_to_id.get(player["mlb_team"])
        sched = schedule_by_team.get(team_id, {}) if team_id else {}
        row_results = []

        for day in days:
            game_info = sched.get(day.isoformat())
            try:
                action, lineup_status = upsert_schedule_row(
                    notion_key, player, day, today_et, game_info, week, existing
                )
                matchup = game_info["matchup"] if game_info else "OFF"
                row_results.append(f"{day.isoformat()[5:]} {matchup}[{lineup_status}]({action[0]})")
                ok += 1
            except Exception as e:
                row_results.append(f"{day.isoformat()[5:]} ERR")
                print(f"  [錯誤] {player['name']} {day.isoformat()}: {e}")
                fail += 1

        print(f"  {player['name']:<28} {' | '.join(row_results)}")

    print(f"\n完成：{ok} 成功 / {fail} 失敗  →  Notion DB2 Schedule")


if __name__ == "__main__":
    main()
