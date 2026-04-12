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
- [ ] **RPi 部署**
  - [ ] 確認 RPi Python 版本（需 3.10+）
  - [ ] git clone 或 rsync 專案到 RPi（`~/fantasy-baseball/`）
  - [ ] pip install 依賴（`yahoo-fantasy-api yahoo_oauth requests`）
  - [ ] scp `oauth2.json` 到 RPi 的 `~/fantasy-baseball/`（勿 commit）
  - [ ] 在 RPi 建立 `~/.config/notion/api_key_new`，貼上 Notion API key
  - [ ] 手動逐一執行 4 支 sync 腳本確認正常（roster → schedule → stats → lineup）
  - [ ] 設定 cron job（注意路徑要用 `sync/` 前綴，非 notion-plan.md 舊路徑）
  - [ ] 等第一次 cron 自動跑後確認 Notion 資料有更新

### 其他功能
- [ ] 投手陣容對戰表（上場日、對手打線強度）
- [ ] 測試寫入：調整先發名單

## 規格確認

- 平台：Yahoo Fantasy Baseball
- 管理範圍：打擊 + 投手
- 執行環境：本機 Mac（開發）→ Raspberry Pi（正式自動化）
- 目標：Notion 一站查閱陣容 / 賽況 / 交易分析，每天 lineup lock 前不需開 Claude Code
