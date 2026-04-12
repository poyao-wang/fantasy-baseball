"""
抓取聯盟靜態資訊（設定、規則、積分類別等）並存到本地 JSON
"""
import json
import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2

sc = OAuth2(None, None, from_file="oauth2.json")
if not sc.token_is_valid():
    sc.refresh_access_token()

gm = yfa.Game(sc, "mlb")
league = gm.to_league("469.l.171948")

# 聯盟設定
settings = league.settings()

# 積分類別
stat_categories = league.stat_categories()

# 所有球隊
teams = league.teams()

output = {
    "settings": settings,
    "stat_categories": stat_categories,
    "teams": teams,
}

with open("league_info.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("=== 聯盟基本資料 ===")
print(f"名稱：{settings['name']}")
print(f"人數：{settings['num_teams']} 隊")
print(f"賽制：{settings['scoring_type']}")
print(f"\n積分類別（{len(stat_categories)} 項）：")
for s in stat_categories:
    print(f"  {s['display_name']} ({s.get('abbr', s.get('stat_id', ''))})")
print(f"\n本地存檔：league_info.json")
