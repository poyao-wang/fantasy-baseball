"""
update_stats.py — 從 Yahoo Fantasy API 拉取球員區間統計，upsert 到 Notion DB3 (Stats)
upsert key: Title（`{Name} W{week} {period}`，例：Altuve W3 7d）
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
from notion_config import NOTION_KEY_PATH, DB_PLAYERS, DB_STATS

LEAGUE_ID = "469.l.171948"
GAME_ID   = "469"  # MLB 2026

# Yahoo API 支援的 stat_type → 我們的 period label
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
    """從 DB1 拉所有球員，回傳含 player_id 的完整 dict"""
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
                player_id = int(player_id_raw)
                players.append({
                    "name":          name,
                    "page_id":       page["id"],
                    "player_id":     player_id,
                    "player_key":    f"{GAME_ID}.p.{player_id}",
                    "position_type": position_type,
                })
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return players


def get_existing_stats_titles(key: str, week: int) -> dict[str, str]:
    """拉 DB3 本週所有 rows，回傳 {title: page_id}（batch query 減少 API 呼叫）"""
    url = f"https://api.notion.com/v1/databases/{DB_STATS}/query"
    body: dict = {
        "page_size": 100,
        "filter": {"property": "Week", "number": {"equals": week}},
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


# ── 統計解析 ──────────────────────────────────────────────────

def parse_stat(raw) -> float | None:
    """把各種格式的 stat value 轉成 float；空值、'-' 回傳 None"""
    if raw is None or raw == "" or raw == "-":
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def extract_stats(player_data: dict, position_type: str) -> dict[str, float | None]:
    """
    從 yahoo-fantasy-api player_stats 回傳的 dict 提取本聯盟積分類別數據。
    library 已依 stat_categories 將 stat_id 映射為 display_name（R / HR / AVG…）作為 key。
    """
    target = BATTER_STATS if position_type == "B" else PITCHER_STATS
    return {stat: parse_stat(player_data.get(stat)) for stat in target}


def fmt_stat(value: float | None, fmt: str = "") -> str:
    if value is None:
        return "-"
    return format(value, fmt)


# ── upsert ────────────────────────────────────────────────────

def build_stats_props(
    player: dict,
    period: str,
    week: int,
    stats: dict[str, float | None],
) -> dict:
    title   = f"{player['name']} W{week} {period}"
    now_iso = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()

    props: dict = {
        "Title":      {"title": [{"text": {"content": title}}]},
        "Player":     {"relation": [{"id": player["page_id"]}]},
        "Week":       {"number": week},
        "Period":     {"select": {"name": period}},
        "Updated_At": {"date": {"start": now_iso}},
    }

    # 只寫入非 None 欄位，避免用空值覆蓋無關位置類型的欄位
    for stat, value in stats.items():
        if value is not None:
            props[stat] = {"number": value}

    return props


def upsert_stats_row(
    key: str,
    player: dict,
    period: str,
    week: int,
    stats: dict[str, float | None],
    existing: dict[str, str],
) -> str:
    """存在則 PATCH，不存在則 POST。回傳 '更新' 或 '新增'"""
    title   = f"{player['name']} W{week} {period}"
    props   = build_stats_props(player, period, week, stats)
    page_id = existing.get(title)

    if page_id:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        r = requests.patch(url, headers=notion_headers(key), json={"properties": props})
    else:
        url = "https://api.notion.com/v1/pages"
        body = {"parent": {"database_id": DB_STATS}, "properties": props}
        r = requests.post(url, headers=notion_headers(key), json=body)

    r.raise_for_status()
    return "更新" if page_id else "新增"


# ── 主程式 ────────────────────────────────────────────────────

def main():
    try:
        notion_key = load_notion_key()

        sc = OAuth2(None, None, from_file="oauth2.json")
        if not sc.token_is_valid():
            sc.refresh_access_token()

        gm     = yfa.Game(sc, "mlb")
        league = gm.to_league(LEAGUE_ID)
        week   = league.current_week()

        print(f"Fantasy Week {week}  →  Notion DB3 Stats\n")

        print("[Notion] 拉取 DB1 球員清單...")
        players = get_all_players(notion_key)
        print(f"  → 共 {len(players)} 人\n")

        print("[Notion] 拉取 DB3 本週已存在 rows...")
        existing = get_existing_stats_titles(notion_key, week)
        print(f"  → 本週已存在 {len(existing)} 筆\n")

        yahoo_ids   = [str(p["player_id"]) for p in players]
        ok, fail    = 0, 0

        for period_label, req_type in PERIODS:
            print(f"[Yahoo] 拉取 {period_label}（{req_type}）stats...")
            try:
                raw_stats = league.player_stats(yahoo_ids, req_type)
            except Exception as e:
                print(f"  [錯誤] 無法取得 {period_label} stats: {e}\n")
                continue

            stats_by_id: dict[int, dict] = {
                item["player_id"]: item
                for item in raw_stats
                if "player_id" in item
            }
            print(f"  → 取得 {len(stats_by_id)} 人數據\n")

            for player in players:
                player_data = stats_by_id.get(player["player_id"], {})
                stats       = extract_stats(player_data, player["position_type"])
                try:
                    action = upsert_stats_row(
                        notion_key, player, period_label, week, stats, existing
                    )
                    if player["position_type"] == "B":
                        summary = (
                            f"AVG={fmt_stat(stats.get('AVG'), '.3f')}  "
                            f"HR={fmt_stat(stats.get('HR'))}  "
                            f"R={fmt_stat(stats.get('R'))}  "
                            f"RBI={fmt_stat(stats.get('RBI'))}  "
                            f"SB={fmt_stat(stats.get('SB'))}"
                        )
                    else:
                        summary = (
                            f"ERA={fmt_stat(stats.get('ERA'), '.2f')}  "
                            f"WHIP={fmt_stat(stats.get('WHIP'), '.3f')}  "
                            f"W={fmt_stat(stats.get('W'))}  "
                            f"SV={fmt_stat(stats.get('SV'))}  "
                            f"K={fmt_stat(stats.get('K'))}"
                        )
                    print(f"  [{action}] {player['name']:<28} {period_label}  {summary}")
                    ok += 1
                except Exception as e:
                    print(f"  [錯誤] {player['name']} {period_label}: {e}")
                    fail += 1

            print()

        print(f"完成：{ok} 成功 / {fail} 失敗  →  Notion DB3 Stats")
        _append_sync_log(f"[update_stats] {ok} 成功 / {fail} 失敗")
    except Exception as e:
        _append_sync_log(f"[update_stats] ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
