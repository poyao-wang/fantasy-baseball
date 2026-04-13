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
- [ ] Step 2：swap_logic.py（OUT 偵測 → BN 候補排名 → swap 清單）
- [ ] Step 3：auto_swap.py（整合 Playwright + swap 邏輯，寫入 sync.log）
- [ ] Step 4：整合進 cron（update_lineup 之後觸發 auto_swap）
- [ ] Step 5：投手策略（依本週 H2H 領先程度決定是否保護 ERA/WHIP）

### 其他功能
- [ ] 投手陣容對戰表（上場日、對手打線強度）

## 規格確認

- 平台：Yahoo Fantasy Baseball
- 管理範圍：打擊 + 投手
- 執行環境：本機 Mac（開發）→ Raspberry Pi（正式自動化）
- 目標：Notion 一站查閱陣容 / 賽況 / 交易分析，每天 lineup lock 前不需開 Claude Code
