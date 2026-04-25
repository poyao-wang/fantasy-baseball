# Fantasy Baseball Manager — Claude 操作指引

## 專案概覽

Yahoo Fantasy Baseball 陣容管理工具。
聯盟：Taiwan X Canada League（`469.l.171948`），我的隊：堯's MVPs（`t.3`）
賽制：H2H，10 積分類別（R, HR, RBI, SB, AVG / W, SV, K, ERA, WHIP）

## 環境

- 開發：Mac，`python3.12`
- 正式：Raspberry Pi 5（`pi5-1.local`，user: `pi`），`python3`
- Yahoo OAuth token：`oauth2.json`（不進 git，`yahoo_oauth` 自動 refresh）
- Notion API key：`~/.config/notion/api_key_new`
- Notion workspace：新 workspace（第二個）

## 資料夾結構

```
scripts/      手動查詢腳本（本機用）
sync/         Notion 同步腳本（RPi cron 用）
data/         靜態資料（league_info.json）
cache/        當日 API 快取（自動產生，不進 git）
output/       輸出 md 檔（自動產生，不進 git）
crontab.txt   Pi5 cron 設定參考（套用：crontab crontab.txt）
```

## Notion DB IDs（詳見 sync/notion_config.py）

| DB | ID |
|----|----|
| DB1 Players | `1eb4bb64-da35-4e9d-b740-f36c8569d3a6` |
| DB2 Schedule | `4bf3af3c-7095-493a-8746-5ad0fc9f147f` |
| DB3 Stats | `d3de639b-94af-44e3-9795-9ac965bb5419` |

## Log 格式

`log.md` 是單一 chronological log，格式：`YYYY-MM-DD HH:MM [類別] 動作`

說「log」時同步更新 `log.md`、`README.md`（結構異動時）、`todo.md`（完成打勾）、`notion-plan.md`（架構異動時）。

## 時間

日期基準為美東時間（ET）。人在日本執行時自動校正。

## Agent Inbox

說「agent inbox」時，將本 session 的重要進展寫入：
`/Users/poyaowang/Documents/projects/life-os/data/agent-inbox.md`

格式：在檔案最上方插入一筆（新的在前）：
```
## YYYY-MM-DD HH:MM [fantasy-baseball] {標題}
{1–3 行摘要，說明做了什麼、現在狀態、下一步}
```

## Yahoo API 知識庫

- `yahoo_fantasy_api` 是**第三方套件**（非官方），底層是打 Yahoo 官方 REST API
- 官方端點：`https://fantasysports.yahooapis.com/fantasy/v2/`
- Stats 可用時間段：`lastweek` / `lastmonth` / `season`，**沒有 `last14days`**
- **Current Ranking 無法從 REST API 取得**，只能靠 Playwright 爬 DOM
  - 球員列表頁 DOM 結構：`cells[6]` = Pre-Season rank，`cells[7]` = Current rank
  - URL 加 `stat1=S_L14` 可讓頁面顯示 14 天 stats（cells[9-14] = H/AB, R, HR, RBI, SB, AVG）
- Ranking 公式推測方向：對球員 stats 跑 z-score 加權，可用 Playwright 爬樣本後做回歸驗證

## 踩坑紀錄

- Mermaid 節點標籤換行必須用 `<br/>`，不能用 `\n`（`\n` 不會被解析，直接顯示成原文）
- MLB Stats API 的 PPD（延賽）比賽仍出現在 schedule 回傳中，`status.detailedState` 為 `"Postponed"`；需主動過濾，否則延賽球員的 `Today_Status` 會被誤判為 `TBD`（非 `OFF`），導致 auto_swap 未觸發換人

## 溝通

繁體中文，口語輕鬆，簡潔不廢話。
