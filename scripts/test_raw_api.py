#!/usr/bin/env python3.12
"""
test_raw_api.py — 直打 Yahoo Fantasy Sports 官方 REST API 測試
看看 player 資源能拿到哪些欄位（stats / ownership / rank）
"""
import json
import requests
from yahoo_oauth import OAuth2

LEAGUE_ID  = "469.l.171948"
GAME_ID    = "469"
BASE       = "https://fantasysports.yahooapis.com/fantasy/v2"

# 拿一個已知球員測試：Vladimir Guerrero Jr. (player_id=7578 in some years)
# 用你 roster 裡確定存在的球員 key 測試
TEST_PLAYER_KEYS = [
    "469.p.10234",   # 先隨便試，會從 league roster 撈
]


def session_headers(sc: OAuth2) -> dict:
    return {"Authorization": f"Bearer {sc.access_token}"}


def get(sc: OAuth2, path: str) -> dict:
    url = f"{BASE}{path}"
    r = requests.get(url, headers=session_headers(sc), params={"format": "json"})
    print(f"  GET {path}  →  {r.status_code}")
    r.raise_for_status()
    return r.json()


def main():
    sc = OAuth2(None, None, from_file="oauth2.json")
    if not sc.token_is_valid():
        sc.refresh_access_token()
    print("OAuth OK\n")

    # ── 1. 拉我的 roster，取出 player_keys ──────────────────────
    print("=== 1. My Roster player_keys ===")
    data = get(sc, f"/team/{GAME_ID}.l.{LEAGUE_ID.split('.l.')[1]}.t.3/roster/players")
    players_raw = (
        data["fantasy_content"]["team"][1]["roster"]["0"]["players"]
    )
    player_keys = []
    for k, v in players_raw.items():
        if k == "count":
            continue
        p = v["player"][0]
        for item in p:
            if isinstance(item, dict) and "player_key" in item:
                pk = item["player_key"]
                name_item = next((x for x in p if isinstance(x, dict) and "full" in x.get("name", {})), None)
                name = ""
                if name_item:
                    name = name_item["name"]["full"]
                player_keys.append((pk, name))
                break
    for pk, name in player_keys[:5]:
        print(f"  {pk}  {name}")
    print(f"  ...共 {len(player_keys)} 人\n")

    # ── 2. 拉前 3 位的 stats（lastweek / last14days / season）──
    print("=== 2. Player Stats（各時間段）===")
    keys_str = ",".join(pk for pk, _ in player_keys[:3])
    for period in ["lastweek", "lastmonth", "season"]:
        try:
            data = get(sc, f"/players;player_keys={keys_str}/stats;type={period}")
            players_node = data["fantasy_content"]["players"]
            for i in range(int(players_node["count"])):
                p = players_node[str(i)]["player"]
                info = p[0]
                name = next((x["name"]["full"] for x in info if isinstance(x, dict) and "name" in x), "?")
                stats_raw = p[1].get("player_stats", {}).get("stats", [])
                print(f"  [{period}] {name}: {stats_raw[:3]}...")
        except Exception as e:
            print(f"  [{period}] 錯誤: {e}")
    print()

    # ── 3. 嘗試 ownership（含 rank）────────────────────────────
    print("=== 3. Player Ownership / Rank ===")
    try:
        data = get(sc, f"/players;player_keys={keys_str}/ownership;type=lastweek")
        print(json.dumps(data["fantasy_content"]["players"]["0"]["player"], indent=2)[:800])
    except Exception as e:
        print(f"  ownership 錯誤: {e}")
    print()

    # ── 4. 嘗試 percent_owned（直接的 percent_started/owned）───
    print("=== 4. Percent Started (7d) ===")
    try:
        data = get(sc, f"/players;player_keys={keys_str}/percent_owned")
        print(json.dumps(data["fantasy_content"]["players"]["0"]["player"], indent=2)[:500])
    except Exception as e:
        print(f"  percent_owned 錯誤: {e}")
    print()

    # ── 5. 拉 draft_analysis（含 ADP，Yahoo 的 ranking）────────
    print("=== 5. Draft Analysis (含 ADP / rank) ===")
    try:
        data = get(sc, f"/players;player_keys={keys_str}/draft_analysis")
        print(json.dumps(data["fantasy_content"]["players"]["0"]["player"], indent=2)[:500])
    except Exception as e:
        print(f"  draft_analysis 錯誤: {e}")


if __name__ == "__main__":
    main()
