"""
add_trade_target.py — 快速新增交易目標到 Notion
用法：
  python3 sync/add_trade_target.py "Player Name"
  python3 sync/add_trade_target.py --id 8967

動作（三步驟）：
  1. Yahoo API 查球員資訊 → upsert DB1 Players（Player_Type = Trade Target）
  2. 建立本週 DB2 Schedule rows（7天）
  3. patch DB1 Stats（AVG_7d/HR_7d… 三區間直接寫回 DB1）
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
from notion_config import NOTION_KEY_PATH, DB_PLAYERS, DB_SCHEDULE

LEAGUE_ID = "469.l.171948"
GAME_ID   = "469"

PERIODS = [
    ("7d",     "lastweek"),
    ("30d",    "lastmonth"),
    ("season", "season"),
]

BATTER_STATS  = {"R", "HR", "RBI", "SB", "AVG"}
PITCHER_STATS = {"W", "SV", "K", "ERA", "WHIP"}


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


def find_schedule_rows_for_player(key: str, player_name: str, week_start: date, week_end: date) -> dict[str, str]:
    """DB2 裡找這位球員本週的 rows，回傳 {title: page_id}"""
    url = f"https://api.notion.com/v1/databases/{DB_SCHEDULE}/query"
    body: dict = {
        "page_size": 100,
        "filter": {
            "and": [
                {"property": "Date", "date": {"on_or_after":  week_start.isoformat()}},
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
            if title.startswith(player_name):
                existing[title] = page["id"]
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return existing




# ── Yahoo 查球員 ──────────────────────────────────────────────

def search_player_by_name(sc, league_id: str, name: str) -> dict | None:
    """
    直接呼叫 Yahoo Fantasy API search 端點查球員姓名，回傳 player dict 或 None。
    player_details() 只接受 player_key，不支援姓名搜尋，所以直接打 API。
    """
    import urllib.parse
    url = (
        f"https://fantasysports.yahooapis.com/fantasy/v2"
        f"/league/{league_id}/players;search={urllib.parse.quote(name)}/stats"
    )
    r = sc.session.get(url, params={"format": "json"})
    if r.status_code != 200:
        return None
    data = r.json()
    try:
        players_data = data["fantasy_content"]["league"][1]["players"]
        if players_data.get("count", 0) == 0:
            return None
        player_meta = players_data["0"]["player"][0]  # list of metadata dicts
        result: dict = {}
        for item in player_meta:
            if not isinstance(item, dict):
                continue
            for k, v in item.items():
                if k == "name":
                    result["name"] = v.get("full", "")
                elif k in ("player_key", "player_id", "editorial_team_abbr",
                           "position_type", "status"):
                    result[k] = v
                elif k == "eligible_positions":
                    result["eligible_positions"] = [
                        pos.get("position", "") for pos in (v if isinstance(v, list) else [])
                        if isinstance(pos, dict)
                    ]
        return result or None
    except (KeyError, IndexError, TypeError):
        return None


def fetch_player_by_key(sc, league_id: str, player_key: str) -> dict | None:
    """
    用 player_key（469.p.12345）查球員資訊，回傳 player dict 或 None。
    """
    url = (
        f"https://fantasysports.yahooapis.com/fantasy/v2"
        f"/league/{league_id}/players;player_keys={player_key}/stats"
    )
    r = sc.session.get(url, params={"format": "json"})
    if r.status_code != 200:
        return None
    data = r.json()
    try:
        players_data = data["fantasy_content"]["league"][1]["players"]
        if players_data.get("count", 0) == 0:
            return None
        player_meta = players_data["0"]["player"][0]
        result: dict = {}
        for item in player_meta:
            if not isinstance(item, dict):
                continue
            for k, v in item.items():
                if k == "name":
                    result["name"] = v.get("full", "")
                elif k in ("player_key", "player_id", "editorial_team_abbr",
                           "position_type", "status"):
                    result[k] = v
                elif k == "eligible_positions":
                    result["eligible_positions"] = [
                        pos.get("position", "") for pos in (v if isinstance(v, list) else [])
                        if isinstance(pos, dict)
                    ]
        return result or None
    except (KeyError, IndexError, TypeError):
        return None


def extract_player_id(p: dict) -> int:
    if "player_id" in p:
        return int(p["player_id"])
    key = p.get("player_key", "")
    return int(key.split(".")[-1])


def normalize_status(p: dict) -> str:
    raw = (p.get("status") or "").upper()
    if "IL" in raw:
        return "IL"
    if "DTD" in raw:
        return "DTD"
    return "Healthy"


# ── DB1 upsert ────────────────────────────────────────────────

def upsert_db1(key: str, p: dict) -> tuple[str, str]:
    """upsert 到 DB1 Players（Trade Target）。回傳 (action, page_id)"""
    player_id = extract_player_id(p)
    eligible  = [pos for pos in p.get("eligible_positions", []) if pos != "Util"]
    props = {
        "Name":               {"title": [{"text": {"content": p["name"]}}]},
        "MLB_Team":           {"select": {"name": p.get("editorial_team_abbr") or "FA"}},
        "Player_Type":        {"select": {"name": "Trade Target"}},
        "Eligible_Positions": {"multi_select": [{"name": pos} for pos in eligible]},
        "Position_Type":      {"select": {"name": p.get("position_type", "B")}},
        "Status":             {"select": {"name": normalize_status(p)}},
        "Player_ID":          {"number": player_id},
    }

    page_id = find_page_by_player_id(key, player_id)
    if page_id:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        r = requests.patch(url, headers=notion_headers(key), json={"properties": props})
    else:
        url = "https://api.notion.com/v1/pages"
        body = {"parent": {"database_id": DB_PLAYERS}, "properties": props}
        r = requests.post(url, headers=notion_headers(key), json=body)

    r.raise_for_status()
    page_id = page_id or r.json()["id"]
    return ("更新" if page_id else "新增"), page_id


# ── DB2 schedule ──────────────────────────────────────────────

def get_mlb_team_ids() -> tuple[dict, dict]:
    r = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1")
    abbr_to_id = {t["abbreviation"]: t["id"] for t in r.json()["teams"]}
    id_to_abbr = {t["id"]: t["abbreviation"] for t in r.json()["teams"]}
    return abbr_to_id, id_to_abbr


def get_team_schedule(team_id: int, start: date, end: date, id_to_abbr: dict) -> dict[str, dict]:
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
            opp_id  = away["team"]["id"] if is_home else home["team"]["id"]
            opp_team = id_to_abbr.get(opp_id, "???")
            side = "vs" if is_home else "@"
            opp_pitcher = (
                away.get("probablePitcher", {}).get("fullName", "TBD")
                if is_home
                else home.get("probablePitcher", {}).get("fullName", "TBD")
            )
            lineups    = game.get("lineups", {})
            lineup_key = "homePlayers" if is_home else "awayPlayers"
            lineup_names = [p.get("fullName", "") for p in lineups.get(lineup_key, [])]
            result[d["date"]] = {
                "matchup": f"{side} {opp_team}",
                "pitcher": opp_pitcher,
                "lineup":  lineup_names,
            }
    return result


def determine_lineup_status(
    player_name: str,
    position_type: str,
    day: date,
    today: date,
    game_info: dict | None,
) -> str:
    if game_info is None:
        return "OFF"
    if position_type == "P":
        return "TBD"
    if day > today:
        return "TBD"
    lineup = game_info.get("lineup", [])
    if not lineup:
        return "TBD"
    return "IN" if player_name in lineup else "OUT"


def upsert_schedule_rows(
    key: str,
    player_name: str,
    player_page_id: str,
    position_type: str,
    mlb_team: str,
    week: int,
    week_start: date,
    week_end: date,
    today: date,
) -> tuple[int, int]:
    """建立本週 7 天 DB2 rows。回傳 (ok, fail)"""
    abbr_to_id, id_to_abbr = get_mlb_team_ids()
    team_id = abbr_to_id.get(mlb_team)
    sched   = get_team_schedule(team_id, week_start, week_end, id_to_abbr) if team_id else {}

    existing = find_schedule_rows_for_player(key, player_name, week_start, week_end)
    days = [week_start + timedelta(days=i) for i in range(7)]
    ok, fail = 0, 0

    for day in days:
        title     = f"{player_name} {day.isoformat()}"
        game_info = sched.get(day.isoformat())
        lineup_status = determine_lineup_status(player_name, position_type, day, today, game_info)
        opponent  = game_info["matchup"] if game_info else ""
        opp_sp    = game_info["pitcher"]  if game_info else ""

        props = {
            "Title":          {"title": [{"text": {"content": title}}]},
            "Player":         {"relation": [{"id": player_page_id}]},
            "Date":           {"date": {"start": day.isoformat()}},
            "Opponent":       {"rich_text": [{"text": {"content": opponent}}]},
            "Opposing_SP":    {"rich_text": [{"text": {"content": opp_sp}}]},
            "Lineup_Status":  {"select": {"name": lineup_status}},
            "Week":           {"number": week},
        }

        try:
            page_id = existing.get(title)
            if page_id:
                url = f"https://api.notion.com/v1/pages/{page_id}"
                r = requests.patch(url, headers=notion_headers(key), json={"properties": props})
                action = "更新"
            else:
                url = "https://api.notion.com/v1/pages"
                r = requests.post(url, headers=notion_headers(key), json={
                    "parent": {"database_id": DB_SCHEDULE}, "properties": props
                })
                action = "新增"
            r.raise_for_status()
            matchup = game_info["matchup"] if game_info else "OFF"
            print(f"    {day.isoformat()[5:]} {matchup:<12} [{lineup_status}] ({action})")
            ok += 1
        except Exception as e:
            print(f"    {day.isoformat()[5:]} 錯誤: {e}")
            fail += 1

    return ok, fail


# ── DB3 stats ─────────────────────────────────────────────────

def parse_stat(raw) -> float | None:
    if raw is None or raw == "" or raw == "-":
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def patch_stats_to_db1(
    key: str,
    league,
    player: dict,
) -> tuple[int, int]:
    """三個 period stats 全部寫回 DB1 player page。回傳 (ok, fail)"""
    target_stats = BATTER_STATS if player["position_type"] == "B" else PITCHER_STATS
    yahoo_id = str(player["player_id"])
    now_iso  = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
    props: dict = {"Stats_Updated_At": {"date": {"start": now_iso}}}
    ok, fail = 0, 0

    for period_label, req_type in PERIODS:
        try:
            raw_list = league.player_stats([yahoo_id], req_type)
            player_data = next((x for x in raw_list if "player_id" in x), {})
            stats = {stat: parse_stat(player_data.get(stat)) for stat in target_stats}
            for stat, val in stats.items():
                if val is not None:
                    props[f"{stat}_{period_label}"] = {"number": val}
            if player["position_type"] == "B":
                summary = (
                    f"AVG={stats.get('AVG') or '-'}  "
                    f"HR={stats.get('HR') or '-'}  "
                    f"R={stats.get('R') or '-'}  "
                    f"RBI={stats.get('RBI') or '-'}  "
                    f"SB={stats.get('SB') or '-'}"
                )
            else:
                summary = (
                    f"ERA={stats.get('ERA') or '-'}  "
                    f"WHIP={stats.get('WHIP') or '-'}  "
                    f"W={stats.get('W') or '-'}  "
                    f"SV={stats.get('SV') or '-'}  "
                    f"K={stats.get('K') or '-'}"
                )
            print(f"    {period_label:<6}  {summary}")
            ok += 1
        except Exception as e:
            print(f"    [錯誤] {period_label}: {e}")
            fail += 1

    try:
        url = f"https://api.notion.com/v1/pages/{player['page_id']}"
        r = requests.patch(url, headers=notion_headers(key), json={"properties": props})
        r.raise_for_status()
    except Exception as e:
        print(f"    [錯誤] PATCH DB1: {e}")
        return 0, len(PERIODS)

    return ok, fail


# ── 主程式 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="新增交易目標球員到 Notion")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("name", nargs="?", help="球員姓名（例：Jose Altuve）")
    group.add_argument("--id", type=int, dest="player_id", help="Yahoo player ID")
    args = parser.parse_args()

    notion_key = load_notion_key()

    # Yahoo auth
    sc = OAuth2(None, None, from_file="oauth2.json")
    if not sc.token_is_valid():
        sc.refresh_access_token()

    gm     = yfa.Game(sc, "mlb")
    league = gm.to_league(LEAGUE_ID)
    week   = league.current_week()

    # 日期基準：美東時間（ET）
    today_et  = datetime.now(ZoneInfo("America/New_York")).date()
    season_start = date(2026, 3, 25)
    week_start   = season_start + timedelta(weeks=week - 1)
    week_end     = week_start + timedelta(days=6)

    print(f"Fantasy Week {week}：{week_start} ～ {week_end}（ET）\n")

    # ── Step 1：查球員資訊 ────────────────────────────────────
    if args.player_id:
        print(f"[Yahoo] 查詢球員 ID = {args.player_id}...")
        p = fetch_player_by_key(sc, LEAGUE_ID, f"{GAME_ID}.p.{args.player_id}")
    else:
        print(f"[Yahoo] 查詢球員：{args.name}...")
        p = search_player_by_name(sc, LEAGUE_ID, args.name)

    if not p:
        print("  找不到球員，請確認姓名或 ID。")
        sys.exit(1)
    player_id = extract_player_id(p)
    player_name = p["name"]
    mlb_team = p.get("editorial_team_abbr") or "FA"
    position_type = p.get("position_type", "B")
    eligible = [pos for pos in p.get("eligible_positions", []) if pos != "Util"]
    status = normalize_status(p)

    print(f"  找到：{player_name}（{mlb_team}，{position_type}，{'/'.join(eligible)}，{status}）\n")

    # ── Step 2：DB1 upsert ───────────────────────────────────
    print("[Notion] DB1 Players — upsert Trade Target...")
    action, player_page_id = upsert_db1(notion_key, p)
    print(f"  [{action}] {player_name}  player_id={player_id}\n")

    # ── Step 3：DB2 schedule ─────────────────────────────────
    print(f"[Notion] DB2 Schedule — 建立本週 7 天 rows...")
    s_ok, s_fail = upsert_schedule_rows(
        notion_key, player_name, player_page_id,
        position_type, mlb_team, week, week_start, week_end, today_et,
    )
    print(f"  → {s_ok} 成功 / {s_fail} 失敗\n")

    # ── Step 4：DB1 stats patch ───────────────────────────────
    print(f"[Notion] DB1 Stats — patch 區間數據（7d / 30d / season）...")
    player_for_stats = {
        "name":          player_name,
        "page_id":       player_page_id,
        "player_id":     player_id,
        "position_type": position_type,
    }
    st_ok, st_fail = patch_stats_to_db1(notion_key, league, player_for_stats)
    print(f"  → {st_ok} 成功 / {st_fail} 失敗\n")

    total_ok   = 1 + s_ok + st_ok
    total_fail = s_fail + st_fail
    print(f"完成：{total_ok} 筆成功 / {total_fail} 筆失敗  →  {player_name} 已加入 Notion 交易目標")


if __name__ == "__main__":
    main()
