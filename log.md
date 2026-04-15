# Fantasy Baseball Manager — Log

---

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

---

## Activity Log

2026-04-12  專案啟動。完成 Yahoo Developer App 申請、OAuth 認證、讀取聯盟資訊（Taiwan X Canada League，10 隊，H2H，10 積分類別）。確認 API 讀取正常，之後視操作紀錄規律再決定腳本方向。

2026-04-12  打者對戰投手表完成。資料來源：Yahoo API（陣容）+ MLB Stats API（賽程/先發投手）。查看自己陣容、對手陣容（金采源的狗）、各打者未來一週對手。發現時區問題（人在日本，日期超前美東一天），改用 ET 時間為基準。

2026-04-12  新增今日打線狀態功能。opponent_schedule.py 在今天那欄顯示 MLB 實際上場名單（✓在打線 / ✗未上場 / ?尚未公布）。lineup 資料每次執行 fresh 拉取，不進快取。驗證：4/11 全隊 9/9 已公布打線，Brendan Donovan（DTD）確認未進打線。

2026-04-12  新增 export_schedule_md.py，將對戰表輸出為 Markdown 檔案（output/schedule_YYYY-MM-DD.md）。先發陣容在上，BN 分隔線後接板凳，今日欄含打線狀態，休息日顯示 —。

2026-04-12  新增 roster_flex.py，陣容彈性一覽。顯示三區塊：①球員可守位置（先發/BN 分組）、②各位置有誰能頂替、③多守位彈性球員排行。目前風險點：2B 備援只有 Donovan（DTD），Donovan 健康後是最大靈活牌。

2026-04-12  規劃 Notion × RPi 自動化架構（notion-plan.md）。3 個 DB：Players（含交易目標）、Schedule（每日賽況）、Stats（區間快照）。RPi cron 每週一全量更新、每小時更新打線狀態。加入交易目標分析功能：add_trade_target.py 一行指令加人，自動建賽程 + 數據，方便與自己球員並列比較。DB3 Stats 採區間快照設計（7d / 14d / 30d / season），方便在不同時間窗下比較球員狀態與交易價值。

2026-04-12  Notion DB 建立完成（新 Workspace）並 curl 驗證結構正確。DB IDs 存入 sync/notion_config.py。資料夾重新整理：scripts/（查詢腳本）、sync/（Notion 同步）、data/（靜態資料），刪除一次性設定腳本。

2026-04-12  sync/update_roster.py 完成。Yahoo API 拉取我的陣容 25 人（打者 + 投手），upsert 到 Notion DB1 Players。25/25 全成功，首次執行全部新增。IL 球員（Holliday / Boyd / Horton）Status 正確標為 IL，DTD（Springer / Donovan）正確標記。

2026-04-12  sync/update_schedule.py 完成。從 DB1 拉 25 人，對應 15 支 MLB 球隊，拉 Week 3（4/8-4/14）賽程，upsert 175 筆到 DB2 Schedule。過去日期查實際打線（IN/OUT），今日打線未公布則 TBD，未來 TBD，投手一律 TBD，休息日 OFF。每週一全量跑一次。

2026-04-12  sync/update_stats.py 完成並驗證。Yahoo API 拉 3 个 period（7d/30d/season），upsert 75 筆到 DB3 Stats（25 人 × 3 periods）。途中修正 player key 格式問題（yahoo_fantasy_api 自動加前綴），改為只傳數字 ID。14d 因 Yahoo 不支援省略。

2026-04-12  sync/update_lineup.py 完成並驗證（兩輪）。第一版只處理打者；第二版加入投手先發邏輯：從 DB1 拉投手清單，打者查 batting lineup（IN/OUT/TBD），投手查 probablePitcher（START = 今日先發 / TBD = 有賽非先發）。驗證：Zack Littell、José Soriano 正確標為 START，其餘投手維持 TBD，打者全 TBD（打線未公布）。

2026-04-12  sync/add_trade_target.py 完成並驗證。一行指令加入交易目標球員：支援姓名或 --id。三步驟自動完成：①upsert DB1 Players（Player_Type = Trade Target）、②建立本週 7 天 DB2 Schedule rows、③upsert DB3 Stats 三個 period。以 Lucas Erceg（KC RP）驗證：11 筆全成功。途中修正 player_details() 不支援姓名搜尋的問題，改為直接呼叫 Yahoo Fantasy API search 端點。至此 Notion 自動化四支 sync 腳本全部完成，剩 RPi 部署。

2026-04-12  RPi 部署啟動。確認 Python 3.11.2（符合需求）。GitHub SSH key（pi5-1 的 id_ed25519.pub）加入 GitHub，認證通過。git clone fantasy-baseball 到 ~/fantasy-baseball/ 成功。venv 建立、依賴安裝、oauth2.json 複製、Notion API key 設定全數完成。手動逐一執行 4 支 sync 腳本驗證通過（roster 25/25、schedule 182/182、stats 78/78、lineup 正確標記 Zack Littell / José Soriano 為 START）。

2026-04-12  加入 sync.log 執行紀錄。四支腳本（update_roster / schedule / stats / lineup）各自在 main() 結束時 append 一行摘要到 ~/fantasy-baseball/sync.log，格式：`YYYY-MM-DD HH:MM JST [腳本名] N 成功 / N 失敗`；crash 時記 ERROR。查看方式：`tail ~/fantasy-baseball/sync.log`

2026-04-12  RPi cron job 設定完成。時區 JST（RPi 系統時區 Asia/Tokyo 確認）。排程：週一 09:00 全量更新（roster → schedule → stats），每日 22:00–翌日 08:00 每小時整點打線更新（lineup）。stdout 導到 /dev/null，摘要由 sync.log 紀錄。第一次 lineup cron 預計今晚 22:00 JST 自動觸發。

2026-04-13  第一次週一全量 cron 驗證通過。09:00 JST 自動觸發：roster 25/25、schedule 182/182、stats 78/78，0 失敗。昨晚 lineup cron（22:00–08:00）也全數正常無誤。系統完整上線。

2026-04-13  Yahoo API Write scope 調查完畢。fspt-w scope 對一般開發者不開放，兩個 App 均確認無法寫入陣容。改走 Playwright 瀏覽器自動化。設計：update_lineup.py 偵測 OUT → auto_swap.py 執行換人（Playwright + 7d 數據排名）。打者先做，投手策略（依 H2H 本週領先保護 ERA/WHIP）下一階段加入。

2026-04-13  Playwright 換人機制完全破解並實測成功。關鍵發現：Yahoo Fantasy 陣容頁（/b1/171948/3）有隱藏 POST form（action=/b1/171948/3/editroster），每個球員對應一個隱藏 SELECT（name=player_id, value=守位）。換人步驟：① 導 /b1/171948 暖身 → ② 導 /b1/171948/3 等 DOM 載入 → ③ 讀各 SELECT 取球員名、player_id、當前守位、可選守位 → ④ JS 設 SELECT.value → ⑤ form.submit() POST 到 editroster。實測：Guerrero Jr. BN→1B、Caratini 1B→BN，POST 200，頁面即時更新。已建 sync/yahoo_playwright.py（session 管理）、sync/_test_swap.py（探索腳本，可刪）。

2026-04-14  打者自動換人完整實作並驗證。新增 Default_Slot 到 DB1（Notion 管理預設先發，setup_default_slot.py 一鍵初始化）。swap_logic.py 偵測今日 OFF/OUT 的預設先發，從 BN 依 7d 評分找最佳替補（位置固定格先配，Util 最後配任意打者）。auto_swap.py 整合 Playwright 一次批次換人，支援 --dry-run 試算。端對端實測：Guerrero Jr.（TOR 今日無賽）自動換下，Caratini 補上 1B 成功。下一步整合進 cron。

2026-04-14  Step 4 完成。RPi 安裝 Playwright + Chromium ARM64，scp session，git pull，RPi dry-run 正常（Vlad Jr OFF→無替補，邏輯正確）。cron 更新：update_lineup → auto_swap → sync_log（每小時），週一全量末尾加 sync_log。新增 sync_log.py，把 sync.log 同步到 Notion Fantasy Sync Log（DB4）。Notion 四個 DB 統一改名加 Fantasy 前綴。今晚 22:00 JST 等候第一次 cron 自動觸發確認。

2026-04-14  swap_logic 換回邏輯修正。原本只有「替補（Replace）」邏輯，缺少換回機制，導致 Vlad Jr. 滯留 BN、Caratini 佔著 1B，以及 Riley↔Muncy 互換錯位問題。新增三階段邏輯：Phase 0 Rebalance（先發格互換對調）、Phase 1 Restore（從 BN 換回預設位）、Phase 2 Replace（原有替補）。auto_swap.py 支援 out_slot 非 BN 情況。RPi 實測三個換人全部成功，Notion 同步正常。

2026-04-15  update_roster.py 除錯：換掉 Abner Uribe 後 Notion 名單仍殘留舊資料，原因是 update_roster.py 只做 upsert 從不清除離隊球員。修正：新增 `fetch_all_my_roster_pages()` 抓取 Notion 所有 My Roster pages，與 Yahoo 現有陣容比對，不在陣容的 pages 呼叫 `archive_page()` 自動移除。執行後 Abner Uribe（player_id=12746）成功 archive，新人 Jeremiah Jackson 自動新增，26/26 全數正確。另新增交易目標 José Caballero（NYY，2B/3B/SS/OF）。
2026-04-16  auto_swap 連環 bug 除錯修正。4/15 Altuve（OUT）未被自動換人，查 RPi journalctl 確認根因：22:00 JST Playwright timeout、23:00 JST Yahoo OAuth expired 兩個問題連發，整個換人窗口被封。修正三處：① Playwright timeout 20s→60s + retry 3 次；② Yahoo API 403 retry + force refresh；③ auto_swap fallback 機制（Jackson 被鎖 → 自動排除重算 → Donovan→2B + PCA→OF）。swap_logic Phase 2.5 同步修正，改用 effective slot 讓 Phase 1 restore 球員也能參與 chain swap。
2026-04-16  swap_logic / update_lineup 重大修正與功能擴充。發現兩個 bug：①Phase 2 用 default_slot 判斷空格，導致已在 BN 的 Muncy 仍觸發 3B 換人，Riley 被多餘移動；②update_lineup 的 any_lineup_published 全域旗標，導致東岸球隊打線先公布後，西岸球隊 Will Smith / Donovan 等全被誤標 OUT。修正：Phase 2 改用 current_slot 判斷；update_lineup 改為撈已公布打線球隊的完整 roster 做 per-team 判斷。新功能：Phase 2.5 Chain Swap（連鎖換人），BN 無替補時從先發格拉人（如 Jackson→2B、PCA→OF）。auto_swap 新增 out_slot 合法性檢查防止鎖定球員造成 chain swap 孤立。cron 修正：sync_log 改用 ; 確保每次都推送 Notion。

2026-04-16  Pi 測試 + 兩個 bug 修正。①auto_swap.py 提早 return 缺少 locked_pids 第三個回傳值，導致 fallback 機制啟動後全部 retry 失敗。②sync_log.py 同分鐘重複 key 時直接略過，不更新 Notion 舊條目，導致最新換人結果無法顯示。兩處均修正並在 Pi 驗證通過。fallback 正常（Jackson 鎖定 → 排除後重算，Donovan→2B + PCA→OF），sync_log 113 筆全數 PATCH 更新 Notion DB4。
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
