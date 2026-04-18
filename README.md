# Fantasy Baseball Manager

Yahoo Fantasy Baseball 陣容管理工具。本機腳本查閱陣容 / 賽況，長期目標是部署到 Raspberry Pi，搭配 Notion 自動化，達到不需開 Claude Code 的日常管理流程。

## 環境

- Python 3.12
- 套件：`yahoo-fantasy-api`, `yahoo_oauth`

## 聯盟資訊

- 名稱：Taiwan X Canada League（`469.l.171948`）
- 我的隊：堯's MVPs（`t.3`）
- 賽制：H2H，10 積分類別（R, HR, RBI, SB, AVG / W, SV, K, ERA, WHIP）

## 資料夾結構

```
fantasy-baseball/
├── scripts/              # 手動查詢腳本
│   ├── opponent_schedule.py    未來一週對戰投手表 + 今日打線狀態
│   ├── export_schedule_md.py   對戰表輸出為 Markdown
│   ├── roster_flex.py          陣容彈性一覽
│   └── fetch_league_info.py    抓取聯盟靜態資訊
├── sync/                 # Notion 同步腳本（RPi cron 用）
│   ├── notion_config.py        Notion DB IDs 設定
│   ├── update_roster.py        陣容 upsert → Fantasy Roster（每週一）+ 自動清除離隊球員
│   ├── update_schedule.py      當週賽程 upsert → Fantasy Schedule（每球員×7天，每週一）
│   ├── update_lineup.py        Current_Slot 同步 → Fantasy Roster + 今日打線狀態 → Fantasy Schedule（每小時）
│   ├── update_stats.py         區間統計快照 upsert → Fantasy Stats（7d/30d/season，每週一）
│   ├── add_trade_target.py     交易目標一鍵加入（Fantasy Roster + Schedule + Stats）
│   ├── yahoo_playwright.py     Yahoo 登入模組，session 存 yahoo_session.json
│   ├── setup_default_slot.py   Fantasy Roster Default_Slot 初始化（一次性）
│   ├── swap_logic.py           OFF/OUT 偵測 → BN 候補依 7d 評分排名 → swap 清單
│   ├── auto_swap.py            Playwright 執行換人，支援 --dry-run，結果寫入 sync.log
│   └── sync_log.py             sync.log → Fantasy Sync Log（cursor 機制，只送新行；429 retry）
├── data/                 # 靜態資料
│   └── league_info.json        聯盟設定、積分類別、球隊列表
├── 0_inbox/              # 暫存資料（不進 git）
├── cache/                # 當日 API 快取（自動產生）
├── output/               # 輸出 md 檔（自動產生）
├── reauth_write.py       # Yahoo OAuth2 重新授權（token 過期時手動執行）
├── oauth2.json           # Yahoo OAuth2 credentials（勿 commit）
├── notion-plan.md        # Notion × RPi 自動化架構規劃
├── log.md
├── todo.md
└── README.md
```

## 執行紀錄

每支 sync 腳本執行後會 append 一行到 `sync.log`：

```
2026-04-12 21:55 JST [update_roster] 25 成功 / 0 失敗
2026-04-12 21:47 JST [update_stats] 78 成功 / 0 失敗
2026-04-14 07:19 JST [update_lineup] Lineup_Status 2更新/19無變動/0失敗 | Current_Slot 5更新/19無變動/0失敗
```

查看最近紀錄：
```bash
tail ~/fantasy-baseball/sync.log
```

crash 時記 `ERROR: <訊息>`，方便排查。

## Cron 排程（RPi，時區 JST）

| 時間 | 腳本 | 說明 |
|------|------|------|
| 每週一 09:00 | roster → schedule → stats → sync_log | 陣容 / 賽程 / 統計全量更新 |
| 每日 18:30 | roster → sync_log | Waiver 結果（約 17:30）後自動同步 Notion |
| 每日 22:00–翌日 08:00，每小時整點 | lineup → auto_swap → sync_log | 打線更新 + 自動換人 |

## 常用指令

```bash
# 查打者未來一週對戰投手（含今日打線狀態）
python3.12 scripts/opponent_schedule.py

# 輸出對戰表 markdown
python3.12 scripts/export_schedule_md.py

# 陣容彈性一覽（可守位置、各位置備援、多守位球員）
python3.12 scripts/roster_flex.py

# 更新聯盟靜態資訊
python3.12 scripts/fetch_league_info.py

# 陣容 upsert → Notion DB1 Players（每週一 / 手動）
python3.12 sync/update_roster.py

# 當週賽程 upsert → Notion DB2 Schedule（每週一 / 手動）
python3.12 sync/update_schedule.py

# DB1 Current_Slot 同步 + DB2 今日打線狀態更新（每小時 / 手動）
python3.12 sync/update_lineup.py

# 區間統計快照 upsert → Notion DB3 Stats（每週一 / 手動）
python3.12 sync/update_stats.py

# 新增交易目標（Fantasy Roster + Schedule + Stats）
python3.12 sync/add_trade_target.py "Jose Altuve"
python3.12 sync/add_trade_target.py --id 8967

# sync.log → Notion Fantasy Sync Log（通常由 cron 自動觸發）
python3.12 sync/sync_log.py
```

## Lineup_Status 說明

| 狀態 | 對象 | 意義 |
|------|------|------|
| `IN` | 打者 | 今日在打線 |
| `OUT` | 打者 | 今日有賽但不在打線 |
| `START` | 投手 | 今日先發 |
| `TBD` | 打者／投手 | 打線未公布 / 投手有賽但非先發 |
| `OFF` | 全部 | 休息日（無比賽） |

## 記錄慣例

說「log」時，Claude 會同步確認並更新以下相關文件：

- `log.md`（System Log + Activity Log）
- `README.md`（結構或指令有異動時）
- `todo.md`（完成打勾、新增待辦）
- `notion-plan.md`（架構設計有異動時）

## 陣容自動換人

Yahoo Fantasy API 不開放 Write scope，陣容寫入改走 Playwright 瀏覽器自動化。

| 腳本 | 說明 |
|------|------|
| `sync/yahoo_playwright.py` | Yahoo 登入模組，session 存 yahoo_session.json |
| `sync/setup_default_slot.py` | Fantasy Roster Default_Slot 初始化（一次性） |
| `sync/swap_logic.py` | OFF/OUT 偵測 → BN 候補依 7d 評分排名 → swap 清單 |
| `sync/auto_swap.py` | Playwright 執行換人，支援 --dry-run，結果寫入 sync.log |

流程：`update_lineup.py` 更新 Lineup_Status + Current_Slot → `auto_swap.py` 四階段換人：
1. **Rebalance**：先發格互換錯位者直接對調（如 Riley↔Muncy）
2. **Restore**：Default_Slot 在先發格但滯留 BN 者換回（如 Vlad Jr.→1B）
3. **Replace**：今日 OFF/OUT 空位由 BN 最佳候補補上
4. **Chain Swap**：BN 無替補時，從其他先發格拉有資格球員，空出的格再由 BN 補（如 Jackson→2B + PCA→OF）

```bash
# 試算（不動 Yahoo）
python3.12 sync/auto_swap.py --dry-run

# 正式執行換人
python3.12 sync/auto_swap.py
```

### Playwright 換人機制

Yahoo Fantasy 陣容頁 `/b1/171948/3` 內有隱藏 POST form：

```
action = /b1/171948/3/editroster
method = post
hidden fields:
  date   = YYYY-MM-DD（ET 日期）
  crumb  = <CSRF token，每次載入頁面不同>
  stat1  = S
  stat2  = D
  jsubmit = Save Changes
```

每個球員對應一個隱藏 `<select name="{player_id}">`，value 為當前守位。
換人步驟：

```python
# 1. 導 /b1/171948 暖身（避免被導回首頁）
# 2. 導 /b1/171948/3，等 domcontentloaded + 3s
# 3. 讀所有 SELECT：name=player_id, value=守位, options=可用守位
# 4. JS 改值（SELECT 是隱藏的，不能用 select_option）
await page.evaluate("""() => {
    document.querySelector("select[name='10621']").value = '1B';
    document.querySelector("select[name='10748']").value = 'BN';
}""")
# 5. 送出 form
await page.evaluate("document.querySelector(\"form[action*='editroster']\").submit()")
```

### 初次登入（存 session）

```bash
# Mac（有頭模式，完成 Yahoo 登入含 2FA 後自動存 session）
python3.12 sync/yahoo_playwright.py

# RPi 部署：在 Mac 登入後 scp session 過去
scp yahoo_session.json pi@pi5-1.local:~/fantasy-baseball/
```

## 注意事項

- `oauth2.json` 已加入 `.gitignore`，不會被 commit
- token 有效期約 1 小時，`yahoo_oauth` 會自動 refresh
- 日期基準為**美東時間（ET）**，人在日本執行時自動校正，不需手動調整
