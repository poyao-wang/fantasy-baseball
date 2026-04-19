# Fantasy Baseball Manager — Log

## System Log

2026-04-12 [Init] 建立專案資料夾
2026-04-12 [Auth] Yahoo OAuth2 認證完成（Consumer Key + Access Token 存入 oauth2.json）
2026-04-12 [Fetch] 聯盟靜態資訊存入 league_info.json
2026-04-12 [Script] opponent_schedule.py — 打者對戰投手表，含本地快取（cache/）
2026-04-12 [Fix] 日期基準改為美東時間（ET），避免人在日本時日期超前一天
2026-04-12 [Feature] opponent_schedule.py 新增今日打線狀態（✓/✗/?），MLB Stats API hydrate=lineups，每次執行 fresh 拉取不受快取影響
2026-04-12 [Script] export_schedule_md.py — 將對戰表輸出為 Markdown 表格（output/schedule_YYYY-MM-DD.md），先發/BN 分隔，含打線狀態
2026-04-12 [Script] roster_flex.py — 陣容彈性一覽，顯示可守位置、各位置備援來源、多守位球員排行，方便傷病時快速判斷頂替方案
2026-04-12 [Plan] Notion 自動化架構規劃完成（notion-plan.md）。3 DB 設計：Players / Schedule / Stats，RPi cron 自動更新，含交易目標分析功能
2026-04-12 [Design] DB3 Stats 改為區間快照：7d / 14d / 30d / season 四個 period，每球員每週 4 筆。Yahoo API stat_type 參數直接支援，累積數據到中後期參考價值低
2026-04-12 [Notion] 在新 Workspace 建立 3 個 DB（Players / Schedule / Stats），DB IDs 存入 sync/notion_config.py，curl 驗證結構正確
2026-04-12 [Refactor] 資料夾整理：腳本移至 scripts/，Notion 相關移至 sync/，靜態資料移至 data/，刪除一次性設定腳本（auth_test.py / complete_auth.py）
2026-04-12 [Sync] sync/update_roster.py — 陣容 upsert 到 Notion DB1 Players，Player_ID 為 key，打者＋投手＋IL 全涵蓋，Status 自動映射（Healthy/DTD/IL）
2026-04-12 [Sync] sync/update_schedule.py — 當週賽程 upsert 到 Notion DB2 Schedule，每球員×7天共 175 筆，首次全新增。批次查詢既有 rows 減少 API 呼叫
2026-04-12 [Fix] update_schedule.py Lineup_Status 修正：加入 hydrate=lineups，過去日期查實際打線 → IN/OUT，投手一律 TBD，未來日期 TBD，休息日 OFF
2026-04-12 [Script] sync/update_stats.py — 球員區間統計快照 upsert 到 DB3 Stats，3 periods（7d/30d/season），Yahoo API 不支援 14d 已省略
2026-04-12 [Fix] update_stats.py player key 修正：yahoo_fantasy_api 自動加 game_id 前綴，只傳數字 ID；lookup 改用 player_id（int）不用 player_key（str）
2026-04-12 [Test] update_stats.py 驗證通過：75 筆全成功（25 人 × 3 periods），數據正確同步到 DB3
2026-04-12 21:01 [Script] sync/update_lineup.py — DB2 今日打線狀態每小時更新，只 PATCH Lineup_Status，跳過無變動 rows 減少 API 呼叫，OFF 自動排除
2026-04-12 21:06 [Redesign] update_lineup.py 投手邏輯重設計：從 DB1 拉投手名單，打者查 batting lineup（IN/OUT/TBD），投手查 probablePitcher（START/TBD），Notion select 新值 START 首次 PATCH 自動建立
2026-04-12 21:13 [Script] sync/add_trade_target.py — 交易目標一鍵加入，支援姓名或 --id，自動 upsert DB1（Trade Target）+ DB2 本週 7 天賽程 + DB3 三個 period 統計快照
2026-04-12 21:18 [Fix] add_trade_target.py 姓名搜尋修正：player_details() 只接受 player_key，改用直接呼叫 Yahoo Fantasy API search 端點（/players;search={name}/stats），解析 JSON 回傳結構取得球員資訊
2026-04-12 21:19 [Test] add_trade_target.py 驗證通過：Lucas Erceg（KC RP）11 筆全成功（DB1×1 + DB2×7 + DB3×3）
2026-04-12 21:31 [Repo] 專案從 life-os 獨立為 standalone repo，移至 ~/Documents/projects/fantasy-baseball/，推送至 GitHub（poyao-wang/fantasy-baseball，private）
2026-04-12 21:31 [Config] 新增 CLAUDE.md（專案指引）、補強 .gitignore（cache/ output/ __pycache__ .env）
2026-04-12 [Deploy] RPi 部署開始：確認 Python 3.11.2、設定 GitHub SSH key（pi5-1）、git clone 完成（~/fantasy-baseball/）
2026-04-12 [Deploy] RPi pip install 完成（venv 建在 ~/fantasy-baseball/venv/）、oauth2.json scp、Notion api_key_new 設定完成
2026-04-12 [Deploy] RPi 手動驗證 4 支腳本全通過：roster 25/25、schedule 182/182、stats 78/78、lineup 2 更新
2026-04-12 [Feature] 四支 sync 腳本加入 sync.log 紀錄：每次執行結尾 append 一行到 ~/fantasy-baseball/sync.log，crash 也記錄 ERROR
2026-04-12 [Deploy] RPi cron job 設定完成：週一 09:00 JST 全量更新（roster/schedule/stats），每日 22:00–08:00 JST 每小時打線更新（lineup）
2026-04-13 09:00 [Cron] 第一次週一全量 cron 自動觸發成功：roster 25/25、schedule 182/182、stats 78/78，0 失敗。昨晚 lineup cron 22:00–08:00 全數正常。
2026-04-13 [Research] Yahoo Fantasy API Write scope 調查：fspt-w scope 對一般開發者帳號不開放，Yahoo Developer Console 只提供 Read。嘗試兩個 App（原 App + claude-code-2）均回傳 invalid_scope 或 OAuth scope 錯誤，確認無法透過 API 寫入陣容。
2026-04-13 [Plan] 陣容自動化改走 Playwright 瀏覽器自動化。架構：update_lineup.py 偵測 OUT → auto_swap.py 用 Playwright 操作 Yahoo Fantasy 網頁換人。打者優先，投手策略（依本週 H2H 領先程度決定是否保護 ERA/WHIP）後續再加。
2026-04-13 [Script] sync/yahoo_playwright.py — Playwright 登入模組。第一次執行有頭瀏覽器讓使用者完成 Yahoo 登入（含 2FA），wait_for_url 自動偵測登入完成，存 session 到 yahoo_session.json（gitignore）。之後 headless 載入 session，自動驗證有效性。提供 get_context() / cleanup() 供其他腳本 import。
2026-04-13 [Research] Playwright 換人機制完全破解。Yahoo Fantasy 陣容管理頁（/b1/171948/3）有一個隱藏 POST form（action=/b1/171948/3/editroster）。form 內每個球員對應一個隱藏 SELECT，name=Yahoo player_id（數字），value=當前守位。換人方式：JS 直接設 SELECT.value → form.submit()。hidden fields：date（ET 日期）、crumb（CSRF token，每次載入不同）、stat1=S、stat2=D、jsubmit=Save Changes。
2026-04-13 [Test] Playwright 換人實測成功。Guerrero Jr.（pid=10621）BN→1B，Caratini（pid=10748）1B→BN。POST 回傳 200，頁面即時更新確認。整套流程：載入 session → 導 /b1/171948 暖身 → 導 /b1/171948/3 → 讀 SELECT → JS 改值 → form.submit()。
2026-04-14 [Feature] DB1 新增 Default_Slot 欄位（sync/setup_default_slot.py），從 Current_Slot 初始化 25 人，供換人邏輯判斷預設先發位置，Notion 端手動管理。
2026-04-14 [Script] sync/swap_logic.py — 打者換人邏輯：偵測 Default_Slot 在先發格且今日 OFF/OUT 的球員，從 BN 找能守該位置且今日 IN/TBD 的替補，依 DB3 7d 評分排名，產生 swap 清單（in=None 代表無替補可用）。
2026-04-14 [Script] sync/auto_swap.py — 整合 swap_logic + Playwright 執行換人。支援 --dry-run 試算，正式執行一次批次 form submit，結果寫入 sync.log。
2026-04-14 [Test] auto_swap 端對端實測成功：Guerrero Jr.（TOR 今日無賽 → OFF）自動換下至 BN，Caratini 補上 1B。POST 200，頁面即時更新確認。打者自動換人機制完整上線。
2026-04-14 [Deploy] RPi 安裝 Playwright 1.58.0 + Chromium ARM64（179MB），scp yahoo_session.json，git pull，RPi dry-run 驗證正常。
2026-04-14 [Cron] RPi cron 更新：每小時 update_lineup → auto_swap → sync_log；週一全量末尾加 sync_log。
2026-04-14 [Feature] sync/sync_log.py — sync.log 同步到 Notion Fantasy Sync Log（DB4）。upsert key=timestamp+script title，status OK/ERROR 自動判斷。本機測試 5 新增 / 1 略過，正常。
2026-04-14 [Notion] 四個 DB 統一改名加 Fantasy 前綴：Fantasy Roster / Fantasy Schedule / Fantasy Stats / Fantasy Sync Log（📋）。notion_config.py 加入 DB_LOGS。
2026-04-14 [Fix] swap_logic.py 新增換回邏輯：Phase 0 Rebalance（先發格互換錯位，如 Riley↔Muncy 直接對調，不經 BN）+ Phase 1 Restore（Default_Slot 在先發格但目前在 BN 者換回，如 Vlad Jr.→1B 踢走 Caratini）。auto_swap.py 新增 out_slot 欄位支援非 BN 目標格。
2026-04-14 [Test] 三個換人問題全部修正並在 RPi 實測：Vlad Jr.→1B、Muncy→3B、Riley→Util，Notion DB1 Current_Slot 同步更新，Fantasy Sync Log 紀錄正常。
2026-04-15 [Fix] update_roster.py 新增離隊清除邏輯：upsert 完成後，比對 Notion My Roster 與 Yahoo 現有陣容，不在陣容的 pages 自動 archive，防止換人/交易後舊球員殘留。
2026-04-15 [Manual] add_trade_target.py：新增交易目標 José Caballero（NYY，2B/3B/SS/OF，ID=60776）到 Notion（DB1×1 + DB2×7 + DB3×3，共 11 筆）。
2026-04-16 [Fix] swap_logic.py Phase 2 改用 current_slot（非 default_slot）判斷需換人的空格，防止已在 BN 的球員重複觸發空格換人（如 Muncy 已被 Yahoo 移至 BN 仍誤觸發 3B 換人）
2026-04-16 [Feature] swap_logic.py 新增 Phase 2.5 Chain Swap：BN 無替補時，從其他先發格找有資格的球員移過去，空出的格再由 BN 補（如 Jackson→2B + PCA→OF 連鎖）
2026-04-16 [Fix] auto_swap.py 新增 out_slot 合法性檢查：out 球員的目標格也需確認在 SELECT 選項內，防止鎖定球員的 chain swap 孤立執行（如 Jackson 已打完被鎖，secondary swap 也自動跳過）
2026-04-16 [Fix] update_lineup.py 打線狀態判斷改為 per-team roster：撈已公布打線球隊的完整 roster，只有自己球隊打線公布了才判斷 OUT（修正西岸球隊 Will Smith / Donovan 等被誤標 OUT 的問題）
2026-04-16 [Cron] RPi cron 修正：每小時排程 auto_swap 後的 && 改成 ;，確保 sync_log.py 無論腳本成敗都執行，Notion Fantasy Sync Log 不漏記錄
2026-04-16 [Debug] Altuve 未自動換人除錯：查 RPi journalctl 確認 22:00 JST 有兩個連環問題：① auto_swap Playwright timeout（wait_for_load_state 20s 太短）② update_lineup Yahoo API "Forbidden access"（OAuth token 過期且 refresh 失敗）
2026-04-16 [Fix] auto_swap.py Playwright timeout 修正：wait_for_load_state 20s → 60s；主程式加入 retry 機制（最多 3 次，間隔 30 秒）
2026-04-16 [Fix] update_lineup.py Yahoo OAuth 錯誤修正：Yahoo API 呼叫加 retry，回 403/Forbidden 時強制 refresh_access_token() 再重試一次
2026-04-16 [Fix] auto_swap.py 新增 locked_pids fallback：偵測到 in 球員不在 Yahoo SELECT（比賽已開始被鎖）時，將該球員加入 excluded_pids，重新呼叫 get_swap_plan() 計算次優方案（如 Jackson 被鎖 → fallback Donovan→2B + PCA→OF）
2026-04-16 [Fix] swap_logic.py Phase 2.5 改用 effective slot：Phase 0/1 計畫後的球員位置（如 Donovan 被 Phase 1 計畫移到 OF）在 Phase 2.5 chain swap 中正確被考慮為可用 mover，而非沿用 DB1 的原始 current_slot（BN）
2026-04-16 [Feature] swap_logic.py 新增 excluded_pids 參數：支援排除指定球員重新計算換人計畫，供 auto_swap fallback 使用
2026-04-16 [Fix] auto_swap.py execute_swaps_async：無有效換人指令的提早 return 路徑只回傳 2 個值（缺少 locked_pids），修正為回傳 (0, fail, locked_pids)
2026-04-16 [Fix] sync_log.py upsert 邏輯：原本存在就直接「略過」，改為 PATCH 更新 message + status，防止同分鐘重複 key（如手動重跑或 fallback）遮蓋最新結果
2026-04-16 [Test] Pi 端對端測試通過：auto_swap fallback 正常（Jackson 已鎖 → 排除後重算，Donovan→2B + PCA→OF），sync_log 113 筆全數 PATCH 更新 Notion DB4
2026-04-16 21:08 [Manual] update_roster.py 手動執行：Ryan Jeffers（BN）+ Jeffrey Springs（P/BN）新增，2 位離隊球員 archive（player_id 11035 & 10748），26/26 成功
2026-04-16 [Cron] RPi 新增每日 18:30 JST（09:30 UTC）cron：update_roster.py → sync_log.py，承接 Waiver Results 約 17:30 更新後自動同步 Notion
2026-04-17 [Struct] 新增 0_inbox/ 資料夾供 temp 資料暫存，加入 .gitignore
2026-04-17 [Schema] DB2 Fantasy Schedule：Player_Type 欄位改為 batterOrPitcherRoll（Rollup），新增 Game_Time / defaultSlotRoll / defaultSlotRollVal
2026-04-17 [Schema] DB3 Fantasy Stats：新增 HPI（Formula，打者綜合強度指標）/ batterOrPitcherRoll / defaultSlotRoll / defaultSlotRollVal；notion-plan.md 整合 Notion AI 變更紀錄
2026-04-17 [Fix] notion-plan.md Mermaid 圖表節點換行修正：`\n` 全部改為 `<br/>`（Mermaid 只認識 `<br/>`，`\n` 會顯示成原文）；教訓寫入 CLAUDE.md 踩坑紀錄
2026-04-18 [Debug] Notion DB4 429 rate limit 根因診斷：sync_log.py 每次全量同步所有 log（最多 182 筆），每筆需 1 次 query API call，每小時 3 次 cron = 546+ calls，4/16 05:00 起觸發持續 rate limit，所有腳本 Sync Log 均無法寫入 Notion
2026-04-18 [Fix] sync_log.py 改為 cursor 機制：sync.log.cursor 記錄已同步行數，每次只處理新增行（1–3 筆/次），根除 429 問題；同時加入 429 自動 retry（指數退避 5/10/20s，最多 3 次）
2026-04-18 [Manual] update_roster.py 手動執行：Notion DB1 更新至 27 人（新球員已補入），Fantasy Sync Log 歷史 182 筆全數補回 Notion DB4
2026-04-18 [Audit] 全腳本 Notion API 429 風險診斷：update_lineup / update_stats / update_schedule 已為 batch 設計無風險；update_roster.py 存在 find_page_by_player_id 逐筆 query 問題（27 次/執行）
2026-04-18 [Refactor] update_roster.py：刪除 find_page_by_player_id 逐筆 query，改用 fetch_all_my_roster_pages batch 預載共用（upsert + 清除），Notion query 27 → 1；Pi5 測試 27/27 通過
2026-04-18 [Refactor] DB3 Stats 重新設計：從「每球員每週 3 筆（7d/30d/season）」改為「每球員 1 筆，stats 展開成 _7d/_30d/_season property 直接覆蓋」，移除 Week/Period 欄位，不保留歷史；Notion DB3 schema 更新、舊 165 筆清除、重新寫入 27 筆；Pi5 測試通過
2026-04-18 [Refactor] DB3 整合進 DB1：update_stats.py 改為直接 PATCH DB1 球員 page（stats_updated_at + 30 個 stat 欄位），省掉獨立 DB3 及其 Relation/Rollup；notion_config.py 移除 DB_STATS；架構從 4 DB 縮為 3 DB；本機 + Pi5 測試 27/27 通過
2026-04-18 [Fix] swap_logic.py + add_trade_target.py 移除 DB_STATS 依賴：swap_logic get_7d_scores 改從 DB1 讀 AVG_7d/HR_7d 等欄位；add_trade_target upsert_stats_rows 改為 patch_stats_to_db1 直接 PATCH DB1 page
2026-04-18 [Verify] Pi5 三條 cron 手動驗證：roster/schedule/stats/sync_log 全數通過；lineup 通過；auto_swap Playwright timeout（Yahoo 網路短暫問題，與 DB3 改動無關）
2026-04-18 [Fix] yahoo_playwright.py _is_session_valid timeout 修正：ET 早上 8–9 點 Yahoo 網站慢導致 60s timeout 後直接 crash；改為 timeout 時 return True（樂觀假設 session 有效），讓後續真正操作去判斷失效
2026-04-18 21:44 [Manual] Pi5 手動執行 update_lineup + auto_swap：3 換人成功（C：Jeffers→BN/Will Smith→C；OF：Donovan→BN/PCA→OF；3B：Riley→BN/Muncy→3B）；sync_log 補跑 7 筆同步 Notion DB4
2026-04-19 [Schema] DB1 新增 Today_Status 欄位（Select: IN/OUT/TBD/OFF/START），取代 DB2 Lineup_Status 作為每小時動態打線狀態來源；Notion API PATCH 建立完成
2026-04-19 [Refactor] update_lineup.py DB2 完全移除：get_db1_my_roster() 一次查詢取代原本三個函數（pitcher names + DB1 slots + DB2 rows）；PATCH Today_Status 到 DB1；MLB teams API 建 team_id→abbrev 對照表判斷 OFF
2026-04-19 [Refactor] swap_logic.py 移除 DB2 依賴：get_all_batters() 直接帶回 today_status（從 DB1 Today_Status 讀取）；移除 get_today_lineup_status()、DB_SCHEDULE import、compute_swap_plan() 的 today_statuses 參數
2026-04-19 [Fix] update_lineup.py MLB schedule API 不含 team abbreviation 欄位：改先拉 /teams?sportId=1 建 id→abbrev mapping，再對照 playing_team_ids 判斷今日出賽球隊
2026-04-19 [Verify] Pi5 手動驗證：update_roster 27/27、update_lineup Today_Status 27 更新（Paul Skenes→START、Donovan→OUT 等正確）、auto_swap dry-run 換人計畫正常（Will Smith→BN/Jeffers→C + Jeffers→BN/Riley→Util）；hourly update 現在只動 DB1，DB2 整週靜態
2026-04-19 [Refactor] Step 4.z 腳本實作完成：新建 setup_db_week.py（一次性：建 DB_Week Notion DB + 寫 26 週次 + DB1 加 14 個 schedule props + Current_Week relation）；update_schedule.py 完整重寫（移除 DB2 建 rows 邏輯，改 PATCH DB1 This_Mon～Next_Sun 14 個 rich_text props，投手確認先發用 bold annotation，支援 --dry-run）；update_lineup.py 新增 hourly schedule props sync（opposing SP 開賽前即時反映）；add_trade_target.py 移除 DB2 7天 rows 建立，改 PATCH DB1 兩週 schedule props；notion_config.py 加入 DB_WEEK 佔位，DB_SCHEDULE 標記 deprecated；待 setup_db_week.py 實際執行後進行驗證
2026-04-19 [Archive] Notion 端 Fantasy Schedule（DB2）與 Fantasy Stats（DB3）正式 archive；所有腳本已不再讀寫，資料保留但退出作業流程
