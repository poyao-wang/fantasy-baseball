"""
auto_swap.py — 打者自動換人（Playwright + Yahoo Fantasy）

流程：
1. 呼叫 swap_logic.get_swap_plan() 取得換人清單
2. 若無需換人，直接結束
3. 開啟 Playwright，載入 Yahoo session
4. 前往陣容頁，讀取 SELECT 結構
5. 一次批次設值後 submit form
6. 結果寫入 sync.log

執行時機：update_lineup.py 之後（每小時 cron 或手動）

用法：
    python3 sync/auto_swap.py          # 正式執行
    python3 sync/auto_swap.py --dry-run  # 試算（只印計畫，不動 Yahoo）
"""
import sys
import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from swap_logic import get_swap_plan
from yahoo_playwright import get_context_async, cleanup_async

LEAGUE_ID = "171948"
TEAM_ID = "3"
TEAM_URL = f"https://baseball.fantasysports.yahoo.com/b1/{LEAGUE_ID}/{TEAM_ID}"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── sync log ──────────────────────────────────────────────────

def _append_sync_log(message: str) -> None:
    log_path = Path(__file__).parent.parent / "sync.log"
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M JST")
    with open(log_path, "a") as f:
        f.write(f"{now} {message}\n")


# ── Playwright 執行 ───────────────────────────────────────────

async def execute_swaps_async(swaps: list[dict]) -> tuple[int, int]:
    """
    用 Playwright 批次執行換人，一次 form submit。
    回傳 (success_count, fail_count)
    success_count = 實際送出的換人對數（不含無替補的空缺）
    """
    actionable = [s for s in swaps if s["in"] is not None]
    if not actionable:
        return 0, 0

    pw, browser, ctx = await get_context_async()
    page = await ctx.new_page()

    try:
        # 暖身：前往聯盟頁（避免直接跳陣容頁被踢回）
        league_url = f"https://baseball.fantasysports.yahoo.com/b1/{LEAGUE_ID}"
        print(f"[auto_swap] 暖身前往 {league_url}...")
        await page.goto(league_url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(2000)

        # 前往球隊陣容頁
        print(f"[auto_swap] 前往陣容頁 {TEAM_URL}...")
        await page.goto(TEAM_URL, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(3000)

        # 確認 editroster form 存在
        roster_form = await page.query_selector("form[action*='editroster']")
        if not roster_form:
            raise RuntimeError("找不到 editroster form，請確認 session 有效並重新登入")

        # 讀取目前所有 SELECT（player_id → current_value, options）
        select_info: list[dict] = await page.evaluate("""() => {
            const selects = document.querySelectorAll("form[action*='editroster'] select");
            return Array.from(selects).map(sel => ({
                player_id: sel.name,
                current_value: sel.value,
                options: Array.from(sel.options).map(o => o.value),
            }));
        }""")
        available_map: dict[str, dict] = {s["player_id"]: s for s in select_info}
        print(f"[auto_swap] 陣容頁共 {len(select_info)} 個 SELECT\n")

        # 建立 JS 換人指令
        js_lines: list[str] = []
        success = 0
        fail = 0

        for swap in actionable:
            out_pid = str(swap["out"]["player_id"])
            in_pid  = str(swap["in"]["player_id"])
            slot    = swap["slot"]
            out_name = swap["out"]["name"]
            in_name  = swap["in"]["name"]

            # 確認兩位球員都在 SELECT 清單裡
            if out_pid not in available_map:
                print(f"  [跳過] {out_name} (pid={out_pid}) 不在 SELECT 清單")
                fail += 1
                continue
            if in_pid not in available_map:
                print(f"  [跳過] {in_name} (pid={in_pid}) 不在 SELECT 清單")
                fail += 1
                continue

            # 確認目標 slot 是 in_player 的合法選項
            in_options = available_map[in_pid]["options"]
            if slot not in in_options:
                print(f"  [跳過] {in_name} 無法守 {slot}（可選：{in_options}）")
                fail += 1
                continue

            js_lines.append(
                f"document.querySelector(\"select[name='{out_pid}']\").value = 'BN';"
            )
            js_lines.append(
                f"document.querySelector(\"select[name='{in_pid}']\").value = '{slot}';"
            )
            print(f"  {slot:<6}  {out_name:<28} → BN")
            print(f"         {in_name:<28} → {slot}")
            success += 1

        if not js_lines:
            print("\n[auto_swap] 無有效換人指令，略過 submit")
            return 0, fail

        print()

        # 執行 JS 設值
        js_script = "\n".join(js_lines)
        await page.evaluate(f"() => {{ {js_script} }}")

        # 一次 submit form
        print("[auto_swap] 提交 editroster form...")
        await page.evaluate(
            "() => { document.querySelector(\"form[action*='editroster']\").submit(); }"
        )
        await page.wait_for_load_state("domcontentloaded", timeout=20_000)
        await page.wait_for_timeout(2000)

        final_url = page.url
        print(f"[auto_swap] 提交後 URL：{final_url}")

        if "login.yahoo.com" in final_url:
            raise RuntimeError("提交後被導回登入頁，session 可能已失效，請重新執行 yahoo_playwright.py")

        return success, fail

    finally:
        await page.close()
        await cleanup_async(pw, browser, ctx)


# ── 主程式 ────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    today_str = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    print(f"[auto_swap] 開始  日期：{today_str}  {'[DRY RUN]' if dry_run else ''}\n")

    try:
        # Step 1：取得換人計畫
        swaps = get_swap_plan(today_str=today_str)

        actionable = [s for s in swaps if s["in"] is not None]
        no_sub     = [s for s in swaps if s["in"] is None]

        if no_sub:
            print("\n[auto_swap] 以下空缺無可用 BN 替補：")
            for s in no_sub:
                print(f"  {s['slot']:<6}  {s['out']['name']} 今日 OUT，無替補")

        if not actionable:
            print("\n[auto_swap] 今日無需換人，結束。")
            _append_sync_log("[auto_swap] 無換人")
            return

        if dry_run:
            print("\n[DRY RUN] 以上為換人計畫，未實際執行。")
            return

        # Step 2：Playwright 執行
        print(f"\n[auto_swap] 執行 {len(actionable)} 個換人...\n")
        success, fail = asyncio.run(execute_swaps_async(swaps))

        print(f"\n[auto_swap] 完成：{success} 換人成功 / {fail} 失敗")

        # sync.log 摘要
        summary = " | ".join(
            f"{s['slot']}:{s['out']['name']}→{s['in']['name']}"
            for s in actionable
            if s["in"]
        )
        _append_sync_log(f"[auto_swap] {success} 換人成功 / {fail} 失敗  ({summary})")

    except Exception as e:
        _append_sync_log(f"[auto_swap] ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
