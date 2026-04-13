"""
swap_logic.py — 打者換人邏輯（batters only）

邏輯：
1. 讀 DB1：取得每位打者的 Default_Slot（預設先發位置）與 Current_Slot
2. 讀 DB2：取得今日 Lineup_Status（OUT 代表今日有賽但不在打線）
3. 找出 Default_Slot 在先發格（C/1B/2B/3B/SS/OF/Util）且今日 OUT 的球員
   → 這些位子需要替補
4. 找出 Current_Slot = BN 且今日 IN/TBD 的球員（可用替補）
5. 依 DB3 7d 評分排名，逐一分配最佳替補
6. 回傳 swap 清單供 auto_swap.py 執行

Swap dict 結構：
{
    "slot": "1B",
    "out": {"player_id": int, "name": str, "current_slot": str},
    "in":  {"player_id": int, "name": str, "current_slot": "BN"} | None,
}
in = None 代表找不到可用替補（不執行換人，僅回報）
"""
import sys
import re
import requests
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from notion_config import NOTION_KEY_PATH, DB_PLAYERS, DB_SCHEDULE, DB_STATS

# 計分的先發格（不含 BN / IL / SP / RP / P）
STARTING_SLOTS = {"C", "1B", "2B", "3B", "SS", "OF", "Util"}


# ── Notion helpers ────────────────────────────────────────────

def load_notion_key() -> str:
    return Path(NOTION_KEY_PATH).expanduser().read_text().strip()


def notion_headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _query_all(key: str, db_id: str, body: dict) -> list[dict]:
    """分頁查詢，回傳全部 results"""
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    pages = []
    while True:
        r = requests.post(url, headers=notion_headers(key), json=body)
        r.raise_for_status()
        data = r.json()
        pages.extend(data["results"])
        if data.get("has_more"):
            body["start_cursor"] = data["next_cursor"]
        else:
            break
    return pages


# ── 資料讀取 ──────────────────────────────────────────────────

def get_all_batters(key: str) -> dict[int, dict]:
    """
    DB1: My Roster 打者（Position_Type = B）
    回傳 {player_id: {name, default_slot, current_slot, eligible_positions, status}}
    """
    pages = _query_all(key, DB_PLAYERS, {
        "page_size": 100,
        "filter": {
            "and": [
                {"property": "Player_Type", "select": {"equals": "My Roster"}},
                {"property": "Position_Type", "select": {"equals": "B"}},
            ]
        },
    })
    result: dict[int, dict] = {}
    for page in pages:
        props = page["properties"]
        pid = props["Player_ID"]["number"]
        if pid is None:
            continue
        pid = int(pid)
        name_list = props["Name"]["title"]
        name = name_list[0]["plain_text"] if name_list else ""
        if not name:
            continue
        # Default_Slot 可能還不存在（欄位剛建立但尚未設值）→ 預設 BN
        default_slot_prop = props.get("Default_Slot", {})
        default_slot = (default_slot_prop.get("select") or {}).get("name") or "BN"
        current_slot = (props["Current_Slot"]["select"] or {}).get("name", "BN")
        eligible = [m["name"] for m in props["Eligible_Positions"]["multi_select"]]
        status = (props["Status"]["select"] or {}).get("name", "Healthy")
        result[pid] = {
            "name": name,
            "default_slot": default_slot,
            "current_slot": current_slot,
            "eligible_positions": eligible,
            "status": status,
        }
    return result


def get_today_lineup_status(key: str, today_str: str) -> dict[str, str]:
    """
    DB2: 今日所有 rows
    回傳 {player_name: lineup_status}
    """
    pages = _query_all(key, DB_SCHEDULE, {
        "page_size": 100,
        "filter": {"property": "Date", "date": {"equals": today_str}},
    })
    result: dict[str, str] = {}
    for page in pages:
        props = page["properties"]
        title_list = props["Title"]["title"]
        title = title_list[0]["plain_text"] if title_list else ""
        name = title.replace(f" {today_str}", "").strip()
        status = (props["Lineup_Status"]["select"] or {}).get("name", "TBD")
        if name:
            result[name] = status
    return result


def get_7d_scores(key: str, player_ids: set[int], name_to_id: dict[str, int]) -> dict[int, float]:
    """
    DB3: Period = 7d，計算每位打者的綜合評分（打者用）
    score = AVG*300 + HR*5 + RBI*2 + R*1 + SB*3
    回傳 {player_id: score}
    """
    pages = _query_all(key, DB_STATS, {
        "page_size": 100,
        "filter": {"property": "Period", "select": {"equals": "7d"}},
    })
    scores: dict[int, float] = {}
    for page in pages:
        props = page["properties"]
        title_list = props["Title"]["title"]
        title = title_list[0]["plain_text"] if title_list else ""
        # Title 格式：「Name W{n} 7d」
        name = re.sub(r"\s+W\d+\s+7d$", "", title).strip()
        pid = name_to_id.get(name)
        if pid is None or pid not in player_ids:
            continue
        avg = (props.get("AVG", {}).get("number") or 0)
        hr  = (props.get("HR",  {}).get("number") or 0)
        rbi = (props.get("RBI", {}).get("number") or 0)
        r   = (props.get("R",   {}).get("number") or 0)
        sb  = (props.get("SB",  {}).get("number") or 0)
        scores[pid] = avg * 300 + hr * 5 + rbi * 2 + r + sb * 3
    return scores


# ── 換人邏輯 ──────────────────────────────────────────────────

def compute_swap_plan(
    batters: dict[int, dict],
    today_statuses: dict[str, str],
    scores: dict[int, float],
) -> list[dict]:
    """
    產生 swap 清單。

    Rules:
    - 「需要替補」：Default_Slot 在先發格 且 今日 Lineup_Status = OUT
    - 「可用替補」：Current_Slot = BN 且 今日 IN 或 TBD 且 Status ≠ IL
    - 非 Util 位子：替補需 Eligible_Positions 含該位置
    - Util 位子：任何打者均可
    - 有多個相同位子空缺（例如 3 OF）→ 依分數排名逐一分配
    - 已分配的替補不重複使用
    """
    # 加上今日狀態
    for pid, info in batters.items():
        info["today_status"] = today_statuses.get(info["name"], "TBD")

    # 找出空缺（Default_Slot 在先發格且今日 OUT）
    empty_slots: list[dict] = []
    for pid, info in batters.items():
        if info["default_slot"] not in STARTING_SLOTS:
            continue
        if info["today_status"] in ("OUT", "OFF"):
            empty_slots.append({
                "slot": info["default_slot"],
                "out": {
                    "player_id": pid,
                    "name": info["name"],
                    "current_slot": info["current_slot"],
                },
            })

    if not empty_slots:
        return []

    # 找可用替補（BN、今日 IN 或 TBD、非 IL）
    available_bench: list[dict] = []
    for pid, info in batters.items():
        if info["current_slot"] != "BN":
            continue
        if info["status"] == "IL":
            continue
        if info["today_status"] not in ("IN", "TBD"):
            continue
        available_bench.append({
            "player_id": pid,
            "name": info["name"],
            "current_slot": "BN",
            "eligible_positions": info["eligible_positions"],
            "score": scores.get(pid, 0.0),
        })

    # 依評分高到低排序
    available_bench.sort(key=lambda x: x["score"], reverse=True)

    assigned_ids: set[int] = set()
    swaps: list[dict] = []

    # 先處理位置固定的格子（非 Util），再處理 Util
    ordered = (
        [s for s in empty_slots if s["slot"] != "Util"]
        + [s for s in empty_slots if s["slot"] == "Util"]
    )

    for empty in ordered:
        slot = empty["slot"]
        candidate = None
        for bench in available_bench:
            if bench["player_id"] in assigned_ids:
                continue
            # Util 接受任何打者；其他位子需確認 Eligible_Positions
            if slot == "Util" or slot in bench["eligible_positions"]:
                candidate = bench
                break

        if candidate:
            assigned_ids.add(candidate["player_id"])
            swaps.append({
                "slot": slot,
                "out": empty["out"],
                "in": {
                    "player_id": candidate["player_id"],
                    "name": candidate["name"],
                    "current_slot": "BN",
                },
            })
        else:
            swaps.append({
                "slot": slot,
                "out": empty["out"],
                "in": None,  # 無可用替補
            })

    return swaps


# ── 主函數 ────────────────────────────────────────────────────

def get_swap_plan(
    notion_key: str | None = None,
    today_str: str | None = None,
    verbose: bool = True,
) -> list[dict]:
    """
    拉取 Notion 資料，計算今日換人清單。
    可直接 import 供 auto_swap.py 呼叫。
    """
    if notion_key is None:
        notion_key = load_notion_key()
    if today_str is None:
        today_str = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    if verbose:
        print(f"[swap_logic] 日期：{today_str}")

    if verbose:
        print("[swap_logic] 讀取 DB1 打者資料...")
    batters = get_all_batters(notion_key)
    if verbose:
        print(f"  → {len(batters)} 位打者")

    name_to_id = {info["name"]: pid for pid, info in batters.items()}

    if verbose:
        print("[swap_logic] 讀取今日 Lineup_Status（DB2）...")
    today_statuses = get_today_lineup_status(notion_key, today_str)
    if verbose:
        print(f"  → {len(today_statuses)} 筆")

    if verbose:
        print("[swap_logic] 讀取 7d 評分（DB3）...")
    scores = get_7d_scores(notion_key, set(batters.keys()), name_to_id)
    if verbose:
        print(f"  → {len(scores)} 筆\n")

    swaps = compute_swap_plan(batters, today_statuses, scores)

    if verbose:
        if swaps:
            print(f"[swap_logic] 需換人 {len(swaps)} 個位子：")
            for s in swaps:
                out_name = s["out"]["name"]
                in_info = s["in"]
                if in_info:
                    score = scores.get(in_info["player_id"], 0)
                    print(f"  {s['slot']:<6}  OUT {out_name:<28} → IN {in_info['name']:<28} (7d score={score:.1f})")
                else:
                    print(f"  {s['slot']:<6}  OUT {out_name:<28} → （無可用替補）")
        else:
            print("[swap_logic] 今日無需換人")

    return swaps


if __name__ == "__main__":
    get_swap_plan()
