"""
sniff_yahoo_api.py — 攔截 Yahoo Fantasy 前端打的所有 API call
目的：找出 Current Ranking 數字從哪個 endpoint 來
執行：python3.12 scripts/sniff_yahoo_api.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "sync"))
from yahoo_playwright import get_context_async, cleanup_async

# 你 roster 頁的 URL（Last 14 Days 的球員列表）
TARGET_URL = "https://baseball.fantasysports.yahoo.com/b1/171948/players?status=ALL&pos=B&cut_type=33&stat1=S_L14&myteam=0&sort=AR&sdir=1&count=0"

KEYWORDS = ["rank", "ranking", "sort", "player", "stat", "fantasy"]


async def sniff():
    pw, browser, ctx = await get_context_async()
    page = await ctx.new_page()

    captured = []

    async def on_response(response):
        url = response.url
        # 只看 Yahoo 相關的 API / JSON 請求
        if not any(k in url for k in ["yahoo.com", "yimg.com"]):
            return
        ctype = response.headers.get("content-type", "")
        if "json" not in ctype and "javascript" not in ctype:
            return
        try:
            body = await response.json()
            text = json.dumps(body)
            # 有 rank 相關字眼才印
            hits = [k for k in KEYWORDS if k in text.lower()]
            if hits:
                captured.append({"url": url, "hits": hits, "body": body})
                print(f"\n{'='*60}")
                print(f"URL: {url}")
                print(f"命中關鍵字: {hits}")
                # 只印前 1000 字
                print(f"Body 前 1000 字:\n{text[:1000]}")
        except Exception:
            pass

    page.on("response", on_response)

    print(f"前往：{TARGET_URL}\n")
    await page.goto(TARGET_URL, wait_until="networkidle", timeout=60_000)

    # 等額外的 lazy load
    await asyncio.sleep(3)

    print(f"\n{'='*60}")
    print(f"共攔截到 {len(captured)} 個含關鍵字的回應")

    # 找最有可能含 ranking 的
    rank_hits = [c for c in captured if "rank" in c["hits"]]
    if rank_hits:
        print(f"\n★ 含 'rank' 的 endpoint：")
        for c in rank_hits:
            print(f"  {c['url']}")
            print(f"  body 前 500 字: {json.dumps(c['body'])[:500]}\n")
    else:
        print("\n沒有找到含 'rank' 的 API 回應")
        print("所有攔截到的 URL：")
        for c in captured:
            print(f"  {c['url']}")

    await page.close()
    await cleanup_async(pw, browser, ctx)


if __name__ == "__main__":
    asyncio.run(sniff())
