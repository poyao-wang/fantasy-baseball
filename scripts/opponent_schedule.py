"""
顯示我的打者陣容未來一週的對戰投手表
資料來源：Yahoo Fantasy API（陣容）+ MLB Stats API（賽程/先發投手/打線）
暫存：cache/opponent_schedule_YYYY-MM-DD.json，當天內重複執行不重新打 API
打線（lineup）每次執行都 fresh 拉取，不受暫存影響
"""
import json
import requests
import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

# ── MLB team 縮寫 → ID 對照 ──────────────────────────────
def get_mlb_team_ids():
    r = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1")
    abbr_to_id = {t["abbreviation"]: t["id"] for t in r.json()["teams"]}
    id_to_abbr = {t["id"]: t["abbreviation"] for t in r.json()["teams"]}
    return abbr_to_id, id_to_abbr

# ── 某隊未來 N 天賽程（含對手先發投手）──────────────────
def get_schedule(team_id, start: date, id_to_abbr: dict, days=7):
    end = start + timedelta(days=days - 1)
    url = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&teamId={team_id}"
        f"&startDate={start}&endDate={end}"
        f"&hydrate=probablePitcher"
    )
    r = requests.get(url)
    result = {}
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
            result[d["date"]] = {
                "matchup": f"{side} {opp_team}",
                "pitcher": opp_pitcher,
            }
    return result

# ── 今日打線（fresh，不暫存）────────────────────────────
def get_today_lineups(team_ids: list, today_date: date) -> dict:
    """
    回傳 {team_id: [fullName, ...]}
    打線未公布時 list 為空
    """
    result = {}
    for team_id in team_ids:
        url = (
            f"https://statsapi.mlb.com/api/v1/schedule"
            f"?sportId=1&teamId={team_id}"
            f"&startDate={today_date}&endDate={today_date}"
            f"&hydrate=lineups"
        )
        r = requests.get(url)
        names = []
        for d in r.json().get("dates", []):
            for game in d.get("games", []):
                lineups = game.get("lineups", {})
                home_id = game["teams"]["home"]["team"]["id"]
                is_home = home_id == team_id
                key = "homePlayers" if is_home else "awayPlayers"
                names.extend(p.get("fullName", "") for p in lineups.get(key, []))
        result[team_id] = names
    return result

# ── 主程式 ────────────────────────────────────────────────
# MLB 賽程以美東時間（ET）為基準，人在日本時本機日期會超前一天
today = datetime.now(ZoneInfo("America/New_York")).date()
cache_file = CACHE_DIR / f"opponent_schedule_{today}.json"  # today = ET date

sc = OAuth2(None, None, from_file="oauth2.json")
if not sc.token_is_valid():
    sc.refresh_access_token()

# 讀暫存（當天已跑過就跳過 API）
if cache_file.exists():
    print(f"[快取] 讀取 {cache_file.name}")
    data = json.loads(cache_file.read_text())
    batters = data["batters"]
    schedule_cache = {int(k): v for k, v in data["schedule_cache"].items()}
    abbr_to_id, id_to_abbr = get_mlb_team_ids()
else:
    gm = yfa.Game(sc, "mlb")
    league = gm.to_league("469.l.171948")
    my_team = league.to_team(league.team_key())
    roster = my_team.roster()

    abbr_to_id, id_to_abbr = get_mlb_team_ids()

    batters = [p for p in roster if p["position_type"] == "B" and p["selected_position"] != "IL"]
    batters.sort(key=lambda p: (0 if p["selected_position"] != "BN" else 1, p["selected_position"]))

    schedule_cache = {}
    for p in batters:
        team_id = abbr_to_id.get(p["editorial_team_abbr"])
        if team_id and team_id not in schedule_cache:
            schedule_cache[team_id] = get_schedule(team_id, today, id_to_abbr)

    cache_file.write_text(json.dumps({
        "batters": batters,
        "schedule_cache": schedule_cache,
    }, ensure_ascii=False, indent=2))
    print(f"[快取] 已存 {cache_file.name}")

dates = [(today + timedelta(days=i)).isoformat() for i in range(7)]
today_iso = today.isoformat()

# 今日打線（每次 fresh 拉取）
all_team_ids = list({abbr_to_id.get(p["editorial_team_abbr"]) for p in batters if abbr_to_id.get(p["editorial_team_abbr"])})
print("[打線] 拉取今日上場名單...")
today_lineups = get_today_lineups(all_team_ids, today)
posted = sum(1 for names in today_lineups.values() if names)
print(f"[打線] {posted}/{len(all_team_ids)} 隊已公布打線\n")

LINEUP_INDICATOR = {True: "✓", False: "✗", None: "?"}

print(f"\n{'球員':<30}", end="")
for d in dates:
    header = d[5:] + ("(今)" if d == today_iso else "")
    print(f"  {header:<16}", end="")
print()
print("-" * (30 + 18 * 7))

for p in batters:
    pos = p["selected_position"]
    status = f"[{p['status']}]" if p["status"] else ""
    label = f"{p['name']} ({pos}){status}"
    team_id = abbr_to_id.get(p["editorial_team_abbr"])
    sched = schedule_cache.get(team_id, {})

    print(f"{label:<30}", end="")
    for d in dates:
        if d in sched:
            matchup = sched[d]["matchup"]
            pitcher = sched[d]["pitcher"]
            if d == today_iso and team_id in today_lineups:
                lineup = today_lineups[team_id]
                if not lineup:
                    indicator = LINEUP_INDICATOR[None]   # 未公布
                elif p["name"] in lineup:
                    indicator = LINEUP_INDICATOR[True]   # 在打線
                else:
                    indicator = LINEUP_INDICATOR[False]  # 不在打線
                cell = f"{indicator} {matchup} {pitcher}"[:17]
            else:
                cell = f"{matchup} {pitcher}"[:17]
        else:
            cell = "OFF"
        print(f"  {cell:<16}", end="")
    print()
