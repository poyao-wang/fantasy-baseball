"""
sniff_html.py — 從 Yahoo Fantasy 球員列表頁的 HTML 找 ranking 數字
目的：確認 ranking 是否嵌在 SSR HTML 或有獨立 API
執行：python3.12 scripts/sniff_html.py
"""
import asyncio, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "sync"))
from yahoo_playwright import get_context_async, cleanup_async

TARGET_URL = (
    "https://baseball.fantasysports.yahoo.com/b1/171948/players"
    "?status=ALL&pos=B&cut_type=33&stat1=S_L14&myteam=0&sort=AR&sdir=1&count=0"
)

# 我們要找的 ranking 數字（Dingler=127, VGJ=42, Caballero=73）
TARGET_RANKS = ["127", "42", "73"]
TARGET_NAMES = ["Dingler", "Guerrero", "Caballero"]

async def sniff():
    pw, browser, ctx = await get_context_async()
    page = await ctx.new_page()

    # 也攔截 pub-api-rw domain 的請求
    pub_api_calls = []

    async def on_response(response):
        url = response.url
        if "pub-api-rw.fantasysports.yahoo.com" in url or "fantasysports.yahooapis.com" in url:
            try:
                body = await response.text()
                pub_api_calls.append({"url": url, "body": body})
            except Exception:
                pass

    page.on("response", on_response)

    print(f"載入：{TARGET_URL}\n")
    try:
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        print(f"  [警告] goto timeout，嘗試繼續: {e.__class__.__name__}")

    # 等球員 table row 出現（最多 30 秒）
    try:
        await page.wait_for_selector("table.players tbody tr", timeout=30_000)
        print("  [OK] 球員 table 已出現")
    except Exception:
        print("  [警告] 找不到 table.players，嘗試繼續")
    await asyncio.sleep(3)

    # ── 1. 從 HTML 找 ranking 數字 ────────────────────────────
    html = await page.content()

    print("=== 1. 在 HTML 中搜尋 ranking 數字 ===")
    for rank in TARGET_RANKS:
        # 找出現 rank 數字的前後 80 字
        for m in re.finditer(re.escape(rank), html):
            ctx_str = html[max(0, m.start()-80):m.end()+80]
            print(f"  [{rank}] ...{ctx_str}...")
            break  # 只印第一個

    # ── 2. 找 HTML 裡嵌入的 JSON (Redux store / Apollo / window.__data) ──
    print("\n=== 2. HTML 裡的嵌入 JSON ===")
    patterns = [
        r'window\.__(?:INITIAL_STATE|data|store|redux)\s*=\s*(\{.{0,200})',
        r'"playerRank"\s*:\s*(\d+)',
        r'"rank"\s*:\s*(\d+)',
        r'"sort_weight"\s*:\s*(["\d.]+)',
        r'"ar"\s*:\s*(["\d.]+)',
        r'S_L14.{0,50}"rank"',
    ]
    for pat in patterns:
        hits = re.findall(pat, html, re.IGNORECASE)
        if hits:
            print(f"  pattern [{pat[:40]}...]: {hits[:3]}")

    # ── 3. 印出 pub-api-rw 的所有 call ───────────────────────
    print(f"\n=== 3. pub-api-rw / yahooapis.com 的 API calls ({len(pub_api_calls)} 個) ===")
    for call in pub_api_calls:
        body_preview = call["body"][:300].replace("\n", " ")
        print(f"\n  URL: {call['url']}")
        print(f"  Body: {body_preview}")

    # ── 4. 找球員名字附近的 rank 欄位 ──────────────────────────
    print("\n=== 4. 球員名字附近的數字 ===")
    for name in TARGET_NAMES:
        pos = html.find(name)
        if pos >= 0:
            chunk = html[pos:pos+400]
            nums = re.findall(r'"(?:rank|ar|sort_weight|ranking)["\s]*:\s*(\d+)', chunk, re.IGNORECASE)
            print(f"  {name} 附近的 rank-like 數字: {nums}")
            print(f"  {name} 附近原文: {chunk[:150]}")

    # ── 5. 讀 window 上的 JS 全域狀態 ───────────────────────
    print("\n=== 5. window 全域狀態 ===")
    for var in ["__INITIAL_STATE__", "__data__", "__store__", "__APP_STATE__", "YMedia", "YAHOO"]:
        try:
            val = await page.evaluate(f"JSON.stringify(window.{var})")
            if val and val != "undefined":
                print(f"  window.{var} 前 300 字: {val[:300]}")
        except Exception:
            pass

    # ── 6. 從 DOM 直接讀 ranking 數字 ────────────────────────
    print("\n=== 6. 從 DOM 讀球員 ranking ===")
    try:
        rows = await page.evaluate("""
            () => {
                const rows = document.querySelectorAll('table tbody tr');
                const results = [];
                rows.forEach(row => {
                    const nameEl = row.querySelector('.ysf-player-name a, .name');
                    const cells = row.querySelectorAll('td');
                    if (nameEl && cells.length > 3) {
                        results.push({
                            name: nameEl.textContent.trim(),
                            cells: Array.from(cells).map(td => td.textContent.trim()).slice(0, 8)
                        });
                    }
                });
                return results.slice(0, 10);
            }
        """)
        for r in rows:
            print(f"  {r['name']}: {r['cells']}")
    except Exception as e:
        print(f"  DOM 讀取失敗: {e}")

    # ── 7. 存 HTML 以備手動分析 ─────────────────────────────
    out = Path(__file__).parent.parent / "output" / "yahoo_players_page.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"\n完整 HTML 已存至：{out}")

    await page.close()
    await cleanup_async(pw, browser, ctx)


if __name__ == "__main__":
    asyncio.run(sniff())
