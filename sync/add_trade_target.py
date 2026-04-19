"""
add_trade_target.py — 快速新增交易目標到 Notion
用法：
  python3 sync/add_trade_target.py "Player Name"
  python3 sync/add_trade_target.py --id 8967

動作（三步驟）：
  1. Yahoo API 查球員資訊 → upsert DB1 Players（Player_Type = Trade Target）
  2. PATCH DB1 兩週 schedule props（This_Mon～Next_Sun）
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
from notion_config import NOTION_KEY_PATH, DB_PLAYERS

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


# ── DB1 schedule props ────────────────────────────────────────

_DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _get_mlb_team_ids() -> tuple[dict, dict]:
    r = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1")
    r.raise_for_status()
    abbr_to_id = {t["abbreviation"]: t["id"] for t in r.json()["teams"]}
    id_to_abbr = {t["id"]: t["abbreviation"] for t in r.json()["teams"]}
    return abbr_to_id, id_to_abbr


def _get_team_schedule_range(team_id: int, start: date, end: date, id_to_abbr: dict) -> dict[str, dict]:
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
            result[d["date"]] = {
                "matchup":     f"{side} {opp_team}",
                "opp_pitcher": opp_side.get("probablePitcher", {}).get("fullName", ""),
                "our_pitcher": our_side.get("probablePitcher", {}).get("fullName", ""),
            }
    return result


def _build_day_value(player_name: str, position_type: str, game_info: dict | None) -> tuple[str, bool]:
    if game_info is None:
        return "", False
    matchup = game_info["matchup"]
    if position_type == "P":
        our = game_info.get("our_pitcher", "")
        return matchup, bool(our) and our == player_name
    else:
        opp = game_info.get("opp_pitcher", "")
        return (f"{matchup} / {opp}" if opp else matchup), False


def _make_rich_text(text: str, bold: bool = False) -> dict:
    if not text:
        return {"rich_text": []}
    item: dict = {"text": {"content": text}}
    if bold:
        item["annotations"] = {"bold": True}
    return {"rich_text": [item]}


def patch_schedule_props_to_db1(
    key: str,
    player_name: str,
    player_page_id: str,
    position_type: str,
    mlb_team: str,
) -> tuple[int, int]:
    """兩週 schedule props PATCH 到 DB1。回傳 (ok, fail)"""
    today_et = datetime.now(ZoneInfo("America/New_York")).date()
    days_since_monday = today_et.weekday()
    this_monday = today_et - timedelta(days=days_since_monday)
    next_monday  = this_monday + timedelta(days=7)
    next_sunday  = next_monday + timedelta(days=6)

    abbr_to_id, id_to_abbr = _get_mlb_team_ids()
    team_id = abbr_to_id.get(mlb_team)
    sched   = _get_team_schedule_range(team_id, this_monday, next_sunday, id_to_abbr) if team_id else {}

    player = {"name": player_name, "position_type": position_type}
    props: dict = {}
    for prefix, week_start in [("This", this_monday), ("Next", next_monday)]:
        for i, day_name in enumerate(_DAY_LABELS):
            date_str = (week_start + timedelta(days=i)).isoformat()
            text, bold = _build_day_value(player_name, position_type, sched.get(date_str))
            props[f"{prefix}_{day_name}"] = _make_rich_text(text, bold)
            if text:
                print(f"    {prefix}_{day_name}: {text}{'  [bold]' if bold else ''}")

    try:
        url = f"https://api.notion.com/v1/pages/{player_page_id}"
        r = requests.patch(url, headers=notion_headers(key), json={"properties": props})
        r.raise_for_status()
        return 1, 0
    except Exception as e:
        print(f"    [錯誤] PATCH DB1 schedule: {e}")
        return 0, 1


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

    today_et = datetime.now(ZoneInfo("America/New_York")).date()
    print(f"今日 ET：{today_et}\n")

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

    # ── Step 3：DB1 schedule props ───────────────────────────
    print(f"[Notion] DB1 Schedule Props — PATCH 兩週賽程...")
    s_ok, s_fail = patch_schedule_props_to_db1(
        notion_key, player_name, player_page_id, position_type, mlb_team,
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
