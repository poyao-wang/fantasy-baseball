"""
陣容彈性一覽：顯示每位球員可守位置，以及各位置有誰可以頂替
資料來自快取（與 opponent_schedule.py 共用），不重新打 API
"""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

today = datetime.now(ZoneInfo("America/New_York")).date()
cache_file = Path("cache") / f"opponent_schedule_{today}.json"

if not cache_file.exists():
    print(f"找不到快取 {cache_file.name}，請先執行 opponent_schedule.py")
    exit(1)

data = json.loads(cache_file.read_text())
batters = data["batters"]

# 起始位置（先發陣容格）
STARTING_SLOTS = ["C", "1B", "2B", "3B", "SS", "OF", "Util"]

# ── 1. 球員清單（依先發/板凳分組） ───────────────────────────
starters = [p for p in batters if p["selected_position"] not in ("BN", "IL")]
bench    = [p for p in batters if p["selected_position"] == "BN"]
il       = [p for p in batters if p["selected_position"] == "IL"]

def fmt_player(p):
    pos_list = [pos for pos in p["eligible_positions"] if pos != "Util"]
    pos_str  = "/".join(pos_list) if pos_list else "Util"
    status   = f" ⚠ {p['status']}" if p["status"] else ""
    slot     = p["selected_position"]
    return f"  {p['name']:<28} [{slot}]  可守：{pos_str}{status}"

print("=" * 65)
print("  陣容彈性一覽")
print("=" * 65)

print("\n【先發】")
for p in starters:
    print(fmt_player(p))

if bench:
    print("\n【板凳 BN】")
    for p in bench:
        print(fmt_player(p))

if il:
    print("\n【傷兵 IL】")
    for p in il:
        print(fmt_player(p))

# ── 2. 各位置備援一覽 ────────────────────────────────────────
print("\n" + "=" * 65)
print("  各位置備援（含先發＋板凳）")
print("=" * 65)

# 找出各位置誰能守（排除 Util）
coverage: dict[str, list] = {slot: [] for slot in STARTING_SLOTS if slot != "Util"}

for p in batters:
    for pos in p["eligible_positions"]:
        if pos in coverage:
            status = f" ⚠{p['status']}" if p["status"] else ""
            slot_label = f"({p['selected_position']})"
            coverage[pos].append(f"{p['name']}{slot_label}{status}")

for pos, players in coverage.items():
    if players:
        print(f"\n  {pos}：")
        for name in players:
            print(f"    - {name}")

# ── 3. 多守位彈性球員 ─────────────────────────────────────────
print("\n" + "=" * 65)
print("  多守位球員（守備彈性最高）")
print("=" * 65)

flex = [(p, [x for x in p["eligible_positions"] if x != "Util"]) for p in batters]
flex = [(p, pos) for p, pos in flex if len(pos) >= 2]
flex.sort(key=lambda x: -len(x[1]))

for p, pos in flex:
    status  = f" ⚠ {p['status']}" if p["status"] else ""
    slot    = p["selected_position"]
    print(f"  {p['name']:<28} [{slot}]  {' / '.join(pos)}{status}")
