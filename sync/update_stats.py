"""
update_stats.py — 從 Yahoo Fantasy API 拉取球員區間統計，直接 upsert 回 Notion DB1 (Players)
upsert key: Player_ID（number property）
periods: 7d (lastweek) / 30d (lastmonth) / season
注意：Yahoo Fantasy API 不支援 14d 區間（無 last14days 參數），已省略
執行時機：每週一 9am JST / 手動
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
GAME_ID   = "469"  # MLB 2026

PERIODS = [
    ("7d",     "lastweek"),
    ("30d",    "lastmonth"),
    ("season", "season"),
]

BATTER_STATS  = {"R", "HR", "RBI", "SB", "AVG"}
PITCHER_STATS = {"W", "SV", "K", "ERA", "WHIP"}


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
    """從 DB1 拉所有球員，回傳含 player_id 與 page_id 的 dict"""
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
            player_id_raw = props["Player_ID"]["number"]
            position_type = (props["Position_Type"]["select"] or {}).get("name", "B")
            if name and player_id_raw is not None:
                players.append({
                    "name":          name,
                    "page_id":       page["id"],
                    "player_id":     int(player_id_raw),
                    "player_key":    f"{GAME_ID}.p.{int(player_id_raw)}",
                    "position_type": position_type,
                })
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return players


# ── 統計解析 ──────────────────────────────────────────────────

def parse_stat(raw) -> float | None:
    if raw is None or raw == "" or raw == "-":
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def extract_stats(player_data: dict, position_type: str) -> dict[str, float | None]:
    target = BATTER_STATS if position_type == "B" else PITCHER_STATS
    return {stat: parse_stat(player_data.get(stat)) for stat in target}


def fmt_stat(value: float | None, fmt: str = "") -> str:
    if value is None:
        return "-"
    return format(value, fmt)


# ── upsert stats ──────────────────────────────────────────────

def patch_player_stats(
    key: str,
    player: dict,
    all_stats: dict[str, dict[str, float | None]],
    pct_owned: float | None = None,
) -> None:
    """all_stats = {"7d": {...}, "30d": {...}, "season": {...}}"""
    now_iso = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
    props: dict = {"Stats_Updated_At": {"date": {"start": now_iso}}}

    if pct_owned is not None:
        props["Pct_Owned"] = {"number": pct_owned / 100}

    for period_label, stats in all_stats.items():
        for stat, value in stats.items():
            if value is not None:
                props[f"{stat}_{period_label}"] = {"number": value}

    url = f"https://api.notion.com/v1/pages/{player['page_id']}"
    r = requests.patch(url, headers=notion_headers(key), json={"properties": props})
    r.raise_for_status()


# ── 主程式 ────────────────────────────────────────────────────

def main():
    try:
        notion_key = load_notion_key()

        sc = OAuth2(None, None, from_file="oauth2.json")
        if not sc.token_is_valid():
            sc.refresh_access_token()

        gm     = yfa.Game(sc, "mlb")
        league = gm.to_league(LEAGUE_ID)

        print("DB1 Stats 更新\n")

        print("[Notion] 拉取 DB1 球員清單...")
        players = get_all_players(notion_key)
        print(f"  → 共 {len(players)} 人\n")

        yahoo_ids = [str(p["player_id"]) for p in players]

        print("[Yahoo] 拉取 Roster% (percent_owned)...")
        try:
            pct_raw = league.percent_owned([int(i) for i in yahoo_ids])
            pct_owned_map: dict[int, float] = {
                item["player_id"]: item["percent_owned"]
                for item in pct_raw
            }
            print(f"  → 取得 {len(pct_owned_map)} 人\n")
        except Exception as e:
            print(f"  [錯誤] 無法取得 percent_owned: {e}\n")
            pct_owned_map = {}

        stats_by_period: dict[str, dict[int, dict]] = {}
        for period_label, req_type in PERIODS:
            print(f"[Yahoo] 拉取 {period_label}（{req_type}）stats...")
            try:
                raw = league.player_stats(yahoo_ids, req_type)
                stats_by_period[period_label] = {
                    item["player_id"]: item
                    for item in raw
                    if "player_id" in item
                }
                print(f"  → 取得 {len(stats_by_period[period_label])} 人\n")
            except Exception as e:
                print(f"  [錯誤] 無法取得 {period_label} stats: {e}\n")
                stats_by_period[period_label] = {}

        ok, fail = 0, 0
        for player in players:
            pid = player["player_id"]
            pos = player["position_type"]

            all_stats = {
                label: extract_stats(stats_by_period.get(label, {}).get(pid, {}), pos)
                for label, _ in PERIODS
            }

            try:
                patch_player_stats(notion_key, player, all_stats, pct_owned_map.get(pid))
                s7 = all_stats["7d"]
                if pos == "B":
                    summary = (
                        f"AVG={fmt_stat(s7.get('AVG'), '.3f')}  "
                        f"HR={fmt_stat(s7.get('HR'))}  "
                        f"R={fmt_stat(s7.get('R'))}  "
                        f"RBI={fmt_stat(s7.get('RBI'))}  "
                        f"SB={fmt_stat(s7.get('SB'))}"
                    )
                else:
                    summary = (
                        f"ERA={fmt_stat(s7.get('ERA'), '.2f')}  "
                        f"WHIP={fmt_stat(s7.get('WHIP'), '.3f')}  "
                        f"W={fmt_stat(s7.get('W'))}  "
                        f"SV={fmt_stat(s7.get('SV'))}  "
                        f"K={fmt_stat(s7.get('K'))}"
                    )
                print(f"  [更新] {player['name']:<28} 7d: {summary}")
                ok += 1
            except Exception as e:
                print(f"  [錯誤] {player['name']}: {e}")
                fail += 1

        print(f"\n完成：{ok} 成功 / {fail} 失敗  →  Notion DB1 Stats")
        _append_sync_log(f"[update_stats] {ok} 成功 / {fail} 失敗")
    except Exception as e:
        _append_sync_log(f"[update_stats] ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
