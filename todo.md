# Fantasy Baseball Manager — 待辦清單

## 完成

- [x] 申請 Yahoo Developer App（Client ID / Client Secret）
- [x] 安裝 Python 套件（`yahoo-fantasy-api`, `yahoo_oauth`）
- [x] OAuth2 認證完成
- [x] 讀取聯盟資訊（`fetch_league_info.py` → `league_info.json`）
- [x] 讀取我的球隊陣容
- [x] 讀取對手陣容（本週對手：金采源的狗）
- [x] 打者對戰投手表（`opponent_schedule.py`，含本地快取）
- [x] 時區修正：日期基準改為美東時間（ET），人在日本也正確
- [x] 今日打線狀態（MLB Stats API `hydrate=lineups`，每次 fresh 拉取，顯示 ✓/✗/?）
- [x] Markdown 輸出（`export_schedule_md.py` → `output/schedule_YYYY-MM-DD.md`）
- [x] 陣容彈性一覽（`roster_flex.py`）
- [x] Notion × RPi 自動化架構規劃（`notion-plan.md`）

## 待處理

### Notion 自動化（優先）
- [x] 在 Notion 建立 3 個 DB（Players / Schedule / Stats）
- [x] 確認 Notion workspace 與 API key（新 workspace，`api_key_new`，DB IDs 存入 `notion_config.py`）
- [x] 寫 `update_roster.py`（DB1 upsert）
- [x] 寫 `update_schedule.py`（DB2 當週賽程）
- [x] 寫 `update_stats.py`（DB3 區間快照：7d / 30d / season，每球員每週 3 筆；Yahoo API 不支援 14d 已省略）
- [x] 寫 `update_lineup.py`（DB2 今日打線狀態，每小時）
- [x] `update_lineup.py` 加入 DB1 Current_Slot 即時同步（輪值調動每小時反映，不等週一）
- [x] 寫 `add_trade_target.py`（交易目標快速加入）
- [x] **RPi 部署**
  - [x] 確認 RPi Python 版本（需 3.10+）→ Python 3.11.2 ✓
  - [x] git clone 或 rsync 專案到 RPi（`~/fantasy-baseball/`）
  - [x] pip install 依賴（`yahoo-fantasy-api yahoo_oauth requests`）→ venv 建在 ~/fantasy-baseball/venv/
  - [x] scp `oauth2.json` 到 RPi 的 `~/fantasy-baseball/`（勿 commit）
  - [x] 在 RPi 建立 `~/.config/notion/api_key_new`，貼上 Notion API key
  - [x] 手動逐一執行 4 支 sync 腳本確認正常（roster → schedule → stats → lineup）→ 全數通過（25/182/78/2更新）
  - [x] sync.log 執行紀錄（每次執行 append 一行，crash 記 ERROR，`tail sync.log` 查看）
  - [x] 設定 cron job（時區 JST，週一 9:00 全量更新，22:00–08:00 每小時打線更新）
  - [x] 等第一次 cron 自動跑後確認 Notion 資料有更新（下週一 2026-04-13 09:00 JST）→ 全數通過（roster 25/schedule 182/stats 78）

### 陣容自動換人（Playwright）
- [x] Step 1：Playwright 登入模組（sync/yahoo_playwright.py，session 存 yahoo_session.json）
- [x] Step 1.5：換人機制破解（隱藏 SELECT + POST form，已實測成功）
- [x] Step 2：swap_logic.py（OFF/OUT 偵測 → BN 候補排名 → swap 清單，依 DB3 7d 評分）
- [x] Step 3：auto_swap.py（整合 Playwright + swap 邏輯，支援 --dry-run，寫入 sync.log）
- [x] Step 4：整合進 cron（update_lineup 之後觸發 auto_swap）
  - [x] RPi 安裝 Playwright 及 Chromium（`pip install playwright && playwright install chromium`）
  - [x] Mac 重新登入存 session（`python3.12 sync/yahoo_playwright.py`）
  - [x] scp `yahoo_session.json` 到 RPi（`scp yahoo_session.json pi@pi5-1.local:~/fantasy-baseball/`）
  - [x] git pull 最新腳本到 RPi
  - [x] RPi 手動測試 `auto_swap.py --dry-run` 確認正常
  - [x] 更新 RPi cron：`update_lineup.py && auto_swap.py`
  - [x] cron 自動觸發確認（22:00 JST，sync.log 有 [auto_swap] 紀錄）
  - [ ] 說明 session 過期處理流程（Mac 重新登入 → scp → RPi 自動恢復）
- [x] **Fix** update_roster.py 離隊清除：upsert 後自動 archive Notion My Roster 中不在 Yahoo 陣容的 pages（修正 Abner Uribe 殘留問題）
- [x] Step 4.5：swap_logic 換回邏輯修正
  - [x] Phase 0 Rebalance：先發格互換錯位（Riley↔Muncy）直接對調
  - [x] Phase 1 Restore：Default_Slot 在先發格但滯留 BN 者換回（Vlad Jr.→1B）
  - [x] auto_swap.py 支援 out_slot 非 BN
  - [x] RPi 實測三個換人全部成功
- [x] Step 4.6：swap_logic / update_lineup bug fix + Chain Swap
  - [x] Phase 2 改用 current_slot 判斷空格（修正已在 BN 球員重複觸發換人）
  - [x] Phase 2.5 Chain Swap：BN 無替補時從先發格連鎖換人（如 Jackson→2B + PCA→OF）
  - [x] auto_swap.py out_slot 合法性檢查（防止鎖定球員 chain swap 孤立執行）
  - [x] update_lineup 改為 per-team roster 判斷 OUT vs TBD（修正西岸球隊誤標 OUT）
  - [x] cron sync_log 改用 ; 確保無論錯誤都推送 Notion
- [x] Step 4.7：auto_swap 穩定性修正 + fallback 機制
  - [x] Playwright timeout 20s → 60s（根因：wait_for_load_state 太短）
  - [x] Playwright retry 3 次（間隔 30 秒）
  - [x] Yahoo OAuth 403 自動 retry + force refresh_access_token
  - [x] locked_pids fallback：被鎖球員排除後重算次優計畫（如 Donovan→2B + PCA→OF）
  - [x] swap_logic Phase 2.5 改用 effective slot（Phase 1 restore 球員可參與 chain swap）
  - [x] swap_logic 新增 excluded_pids 參數供 fallback 使用
- [x] Step 4.8：sync_log.py Notion 429 rate limit 修正
  - [x] 改用 cursor 機制（sync.log.cursor），只同步新增行（1–3 筆/次，原本全量 182 筆）
  - [x] 加入 429 自動 retry（指數退避 5/10/20s，最多 3 次）
- [x] Step 4.9：全腳本 Notion API 429 風險審查 + update_roster.py batch query 優化
  - [x] 診斷所有 sync 腳本 API 呼叫模式（update_lineup / stats / schedule 無問題）
  - [x] update_roster.py：刪除 find_page_by_player_id 逐筆 query，改用 fetch_all_my_roster_pages batch 共用（query 27→1）；Pi5 測試通過
- [x] Step 4.10：DB3 架構簡化 + 整合進 DB1
  - [x] DB3 Stats 改為每球員 1 筆，stats 展開成 _7d/_30d/_season property，移除 Week/Period
  - [x] Notion DB3 schema 更新（API PATCH），舊 165 筆清除，重新寫入 27 筆
  - [x] DB3 整合進 DB1：update_stats.py 直接 PATCH DB1 球員 page
  - [x] swap_logic.py get_7d_scores 改從 DB1 讀 _7d 欄位（移除 DB_STATS）
  - [x] add_trade_target.py upsert_stats_rows → patch_stats_to_db1（移除 DB_STATS）
  - [x] notion_config.py 移除 DB_STATS，notion-plan.md 架構更新（4 DB → 3 DB）
  - [x] Pi5 三條 cron 手動驗證全通過（roster/schedule/stats/lineup）
- [x] Step 4.11：yahoo_playwright.py session 驗證 timeout 修正
  - [x] _is_session_valid timeout 時 return True（樂觀假設），避免 ET 早上 8–9 點 Yahoo 慢時直接 crash
  - [x] Pi5 手動驗證：3 換人成功（C/OF/3B 換回）
- [ ] Step 5：投手策略（依本週 H2H 領先程度決定是否保護 ERA/WHIP）

### 其他功能
- [ ] 投手陣容對戰表（上場日、對手打線強度）

## 規格確認

- 平台：Yahoo Fantasy Baseball
- 管理範圍：打擊 + 投手
- 執行環境：本機 Mac（開發）→ Raspberry Pi（正式自動化）
- 目標：Notion 一站查閱陣容 / 賽況 / 交易分析，每天 lineup lock 前不需開 Claude Code
