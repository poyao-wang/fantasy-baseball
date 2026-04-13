"""
yahoo_playwright.py — Yahoo Fantasy 瀏覽器登入模組

用途：提供已登入的 Playwright BrowserContext，供 auto_swap.py 使用。
session 存在專案根目錄 yahoo_session.json（勿 commit）。

第一次執行（或 session 失效）：
    python3 sync/yahoo_playwright.py
    → 有頭瀏覽器開啟，手動完成 Yahoo 登入（含 2FA），存 session。

之後腳本直接 import get_context() 即可拿到已登入的 context。
"""
import sys
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext

SESSION_FILE = Path(__file__).parent.parent / "yahoo_session.json"
FANTASY_URL = "https://baseball.fantasysports.yahoo.com/"
LOGIN_URL = "https://login.yahoo.com/"


async def _is_session_valid(context: BrowserContext) -> bool:
    """導向 Fantasy 首頁，看是否被踢回登入頁"""
    page = await context.new_page()
    try:
        await page.goto(FANTASY_URL, wait_until="domcontentloaded", timeout=20_000)
        return "login.yahoo.com" not in page.url
    finally:
        await page.close()


async def _interactive_login(playwright) -> BrowserContext:
    """有頭瀏覽器讓使用者手動登入，完成後回傳 context"""
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()

    print("[yahoo_playwright] 開啟瀏覽器，請在瀏覽器中完成 Yahoo 登入（含 2FA）...")
    print("[yahoo_playwright] 登入成功後腳本會自動繼續（等待最多 3 分鐘）")
    await page.goto(FANTASY_URL)

    # 如果被導到登入頁，等使用者完成登入後 URL 回到 Fantasy
    if "login.yahoo.com" in page.url:
        await page.wait_for_url(
            "**/baseball.fantasysports.yahoo.com/**",
            timeout=180_000,
        )

    # 確認在 Fantasy 頁面
    if "login.yahoo.com" in page.url:
        await browser.close()
        raise RuntimeError("登入失敗或尚未完成，請重新執行。")

    print("[yahoo_playwright] 登入成功，存 session...")
    await context.storage_state(path=str(SESSION_FILE))
    print(f"[yahoo_playwright] Session 已存至 {SESSION_FILE}")

    await page.close()
    return context


async def get_context_async():
    """
    回傳已登入的 BrowserContext（async 版）。
    呼叫方負責 context / browser 的關閉。
    """
    playwright = await async_playwright().start()

    if SESSION_FILE.exists():
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=str(SESSION_FILE))
        if await _is_session_valid(context):
            print("[yahoo_playwright] Session 有效，使用既有登入。")
            return playwright, browser, context
        print("[yahoo_playwright] Session 已失效，重新登入...")
        await context.close()
        await browser.close()

    # 需要互動登入
    context = await _interactive_login(playwright)
    browser = context.browser
    return playwright, browser, context


def get_context():
    """
    同步包裝，供不使用 async 的腳本呼叫。
    回傳 (playwright, browser, context)，用完請呼叫 cleanup()。

    範例：
        pw, browser, ctx = get_context()
        page = asyncio.run(_do_something(ctx))
        cleanup(pw, browser, ctx)
    """
    return asyncio.run(get_context_async())


async def cleanup_async(playwright, browser, context):
    await context.close()
    await browser.close()
    await playwright.stop()


def cleanup(playwright, browser, context):
    asyncio.run(cleanup_async(playwright, browser, context))


# ── 直接執行時：強制重新登入存 session ────────────────────────

async def _reauth():
    """強制重新互動登入，不管 session 是否存在。"""
    playwright = await async_playwright().start()
    context = await _interactive_login(playwright)
    await cleanup_async(playwright, context.browser, context)
    print("[yahoo_playwright] 完成，可執行其他 sync 腳本了。")


if __name__ == "__main__":
    reauth = "--reauth" in sys.argv or not SESSION_FILE.exists()
    if reauth:
        asyncio.run(_reauth())
    else:
        # 檢查現有 session
        async def _check():
            pw, browser, ctx = await get_context_async()
            print("[yahoo_playwright] Session 正常，無需重新登入。")
            await cleanup_async(pw, browser, ctx)
        asyncio.run(_check())
