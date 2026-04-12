"""
opponent_schedule cache → markdown 表格
輸出：output/schedule_YYYY-MM-DD.md（以美東 ET 日期命名）
打線狀態每次 fresh 拉取（✓/✗/?）
"""
import json
import requests
from datetime import date, timedelta, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CACHE_DIR = Path("cache")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

today = datetime.now(ZoneInfo("America/New_York")).date()
cache_file = CACHE_DIR / f"opponent_schedule_{today}.json"

if not cache_file.exists():
    print(f"[錯誤] 找不到 {cache_file.name}，請先執行 opponent_schedule.py")
    exit(1)

data = json.loads(cache_file.read_text())
batters = data["batters"]
schedule_cache = {int(k): v for k, v in data["schedule_cache"].items()}

# ── MLB team ID 對照 ─────────────────────────────────────
def get_mlb_team_ids():
    r = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1")
    abbr_to_id = {t["abbreviation"]: t["id"] for t in r.json()["teams"]}
    return abbr_to_id

# ── 今日打線（fresh）────────────────────────────────────
def get_today_lineups(team_ids: list, today_date: date) -> dict:
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

print("[打線] 拉取今日上場名單...")
abbr_to_id = get_mlb_team_ids()
all_team_ids = list({abbr_to_id.get(p["editorial_team_abbr"]) for p in batters if abbr_to_id.get(p["editorial_team_abbr"])})
today_lineups = get_today_lineups(all_team_ids, today)
posted = sum(1 for names in today_lineups.values() if names)
print(f"[打線] {posted}/{len(all_team_ids)} 隊已公布打線")

# ── 組 markdown ──────────────────────────────────────────
today_iso = today.isoformat()
dates = [(today + timedelta(days=i)).isoformat() for i in range(7)]

def cell_text(player, d, team_id, sched):
    if d not in sched:
        return "—"
    matchup = sched[d]["matchup"]
    pitcher = sched[d]["pitcher"]
    base = f"{matchup} · {pitcher}"
    if d == today_iso and team_id in today_lineups:
        lineup = today_lineups[team_id]
        if not lineup:
            indicator = "?"
        elif player["name"] in lineup:
            indicator = "✓"
        else:
            indicator = "✗"
        return f"{indicator} {base}"
    return base

lines = []
lines.append(f"# 堯's MVPs — 打者對戰表")
lines.append(f"")
lines.append(f"更新：{today_iso}（ET）　打線狀態：✓ 在打線 ／ ✗ 未上場 ／ ? 尚未公布")
lines.append(f"")

# 表頭
header_dates = [f"**{d[5:]}**{'（今）' if d == today_iso else ''}" for d in dates]
lines.append("| 球員 | Pos | 狀態 | " + " | ".join(header_dates) + " |")
lines.append("|------|-----|------|" + "|".join(["------"] * len(dates)) + "|")

# 先發 / BN 分隔
starters = [p for p in batters if p["selected_position"] != "BN"]
bench    = [p for p in batters if p["selected_position"] == "BN"]

def player_row(p):
    team_id = abbr_to_id.get(p["editorial_team_abbr"])
    sched = schedule_cache.get(team_id, {})
    pos = p["selected_position"]
    status = p["status"] or ""
    cells = [cell_text(p, d, team_id, sched) for d in dates]
    return f"| {p['name']} | {pos} | {status} | " + " | ".join(cells) + " |"

for p in starters:
    lines.append(player_row(p))

lines.append(f"| **— BN —** | | | " + " | ".join([""] * len(dates)) + " |")

for p in bench:
    lines.append(player_row(p))

output_file = OUTPUT_DIR / f"schedule_{today_iso}.md"
output_file.write_text("\n".join(lines), encoding="utf-8")
print(f"[完成] 輸出 → {output_file}")
