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
│   ├── update_roster.py        陣容 upsert → Notion DB1 Players
│   ├── update_schedule.py      當週賽程 upsert → Notion DB2 Schedule（每球員×7天）
│   ├── update_lineup.py        今日打線狀態更新 → Notion DB2 Lineup_Status（每小時）
│   ├── update_stats.py         區間統計快照 upsert → Notion DB3 Stats（7d/30d/season）
│   └── add_trade_target.py     交易目標一鍵加入（DB1 + DB2 本週賽程 + DB3 統計）
├── data/                 # 靜態資料
│   └── league_info.json        聯盟設定、積分類別、球隊列表
├── cache/                # 當日 API 快取（自動產生）
├── output/               # 輸出 md 檔（自動產生）
├── oauth2.json           # Yahoo OAuth2 credentials（勿 commit）
├── notion-plan.md        # Notion × RPi 自動化架構規劃
├── log.md
├── todo.md
└── README.md
```

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

# 今日打線狀態更新 → Notion DB2（每小時 / 手動）
python3.12 sync/update_lineup.py

# 區間統計快照 upsert → Notion DB3 Stats（每週一 / 手動）
python3.12 sync/update_stats.py

# 新增交易目標（DB1 + DB2 本週賽程 + DB3 統計）
python3.12 sync/add_trade_target.py "Jose Altuve"
python3.12 sync/add_trade_target.py --id 8967
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

## 注意事項

- `oauth2.json` 已加入 `.gitignore`，不會被 commit
- token 有效期約 1 小時，`yahoo_oauth` 會自動 refresh
- 日期基準為**美東時間（ET）**，人在日本執行時自動校正，不需手動調整
