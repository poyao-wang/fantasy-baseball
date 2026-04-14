"""
swap_logic.py — 打者換人邏輯（batters only）

兩階段邏輯：

Phase 1 — Restore（換回）
  條件：Default_Slot 在先發格，且目前在 BN，且今日 IN/TBD
  行動：找出「佔著該格但 Default_Slot 不是該格」的球員（intruder），
        把 intruder 換下 BN，把原主人換回預設位。

Phase 2 — Replace（替補）
  條件：Default_Slot 在先發格，且今日 OUT 或 OFF
  行動：從 BN（含 Phase 1 換下的 intruder）找今日 IN/TBD 的最佳候補補上。

Swap dict 結構：
{
    "slot": "1B",
    "out": {"player_id": int, "name": str, "current_slot": str} | None,
    "in":  {"player_id": int, "name": str, "current_slot": "BN"} | None,
    "restore": bool,   # True = Phase 1 換回，False = Phase 2 替補
}
in = None 代表找不到可用替補（不執行換人，僅回報）
out = None 代表格子是空的（理論上不會發生，防禦性處理）
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
    產生 swap 清單（Phase 1 換回 + Phase 2 替補）。
    """
    # 加上今日狀態
    for pid, info in batters.items():
        info["today_status"] = today_statuses.get(info["name"], "TBD")

    # 建立 slot → 目前佔用者清單（先發格才追蹤）
    slot_occupants: dict[str, list[dict]] = {}
    for pid, info in batters.items():
        cs = info["current_slot"]
        if cs not in STARTING_SLOTS:
            continue
        slot_occupants.setdefault(cs, []).append({
            "player_id": pid,
            "name": info["name"],
            "default_slot": info["default_slot"],
            "current_slot": cs,
            "score": scores.get(pid, 0.0),
        })

    swaps: list[dict] = []
    displaced_ids: set[int] = set()   # Phase 1 換下到 BN 的球員
    restored_ids: set[int] = set()    # Phase 1 換回先發的球員

    # ── Phase 1: Restore（換回）─────────────────────────────
    # 條件：Default_Slot 在先發格 且 Current_Slot = BN 且 今日 IN/TBD 且 非 IL
    restore_candidates = sorted(
        [
            {
                "player_id": pid,
                "name": info["name"],
                "default_slot": info["default_slot"],
                "eligible_positions": info["eligible_positions"],
                "score": scores.get(pid, 0.0),
            }
            for pid, info in batters.items()
            if info["default_slot"] in STARTING_SLOTS
            and info["current_slot"] == "BN"
            and info["status"] != "IL"
            and info["today_status"] in ("IN", "TBD")
        ],
        key=lambda x: x["score"],
        reverse=True,
    )

    for cand in restore_candidates:
        target = cand["default_slot"]
        # 找出佔著該格但 Default_Slot ≠ 該格的球員（intruder）
        intruders = [
            o for o in slot_occupants.get(target, [])
            if o["default_slot"] != target and o["player_id"] not in displaced_ids
        ]
        if not intruders:
            continue  # 格子裡都是應該在的人，不需換回
        # 踢分數最低的 intruder
        intruder = min(intruders, key=lambda x: x["score"])
        swaps.append({
            "slot": target,
            "out": {"player_id": intruder["player_id"], "name": intruder["name"], "current_slot": target},
            "in":  {"player_id": cand["player_id"], "name": cand["name"], "current_slot": "BN"},
            "restore": True,
        })
        displaced_ids.add(intruder["player_id"])
        restored_ids.add(cand["player_id"])

    # ── Phase 2: Replace（替補）──────────────────────────────
    # 條件：Default_Slot 在先發格 且 今日 OUT 或 OFF
    empty_slots: list[dict] = []
    for pid, info in batters.items():
        if info["default_slot"] not in STARTING_SLOTS:
            continue
        if info["today_status"] not in ("OUT", "OFF"):
            continue
        empty_slots.append({
            "slot": info["default_slot"],
            "out": {
                "player_id": pid,
                "name": info["name"],
                "current_slot": info["current_slot"],
            },
        })

    if empty_slots:
        # 可用替補：原本在 BN（非換回者）+ Phase 1 換下的 intruder，今日 IN/TBD 且非 IL
        available_bench: list[dict] = []
        for pid, info in batters.items():
            if info["status"] == "IL":
                continue
            if info["today_status"] not in ("IN", "TBD"):
                continue
            if pid in restored_ids:
                continue  # 已被 Phase 1 換上先發
            is_original_bn = (info["current_slot"] == "BN" and pid not in restored_ids)
            is_displaced   = (pid in displaced_ids)
            if is_original_bn or is_displaced:
                available_bench.append({
                    "player_id": pid,
                    "name": info["name"],
                    "current_slot": "BN",
                    "eligible_positions": info["eligible_positions"],
                    "score": scores.get(pid, 0.0),
                })
        available_bench.sort(key=lambda x: x["score"], reverse=True)

        assigned_ids: set[int] = set(restored_ids)

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
                if slot == "Util" or slot in bench["eligible_positions"]:
                    candidate = bench
                    break
            if candidate:
                assigned_ids.add(candidate["player_id"])
                swaps.append({
                    "slot": slot,
                    "out": empty["out"],
                    "in": {"player_id": candidate["player_id"], "name": candidate["name"], "current_slot": "BN"},
                    "restore": False,
                })
            else:
                swaps.append({
                    "slot": slot,
                    "out": empty["out"],
                    "in": None,
                    "restore": False,
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
                out_name = s["out"]["name"] if s["out"] else "(空格)"
                tag = " [換回]" if s.get("restore") else ""
                in_info = s["in"]
                if in_info:
                    score = scores.get(in_info["player_id"], 0)
                    print(f"  {s['slot']:<6}  OUT {out_name:<28} → IN {in_info['name']:<28} (7d score={score:.1f}){tag}")
                else:
                    print(f"  {s['slot']:<6}  OUT {out_name:<28} → （無可用替補）")
        else:
            print("[swap_logic] 今日無需換人")

    return swaps


if __name__ == "__main__":
    get_swap_plan()
