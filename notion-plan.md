# Fantasy Baseball × Notion 自動化架構規劃

## 系統架構

```mermaid
flowchart TD
    subgraph Sources["資料來源"]
        Y[Yahoo Fantasy API\n陣容 / 積分 / 球員數據]
        M[MLB Stats API\n賽程 / 先發投手 / 打線]
    end

    subgraph RPi["Raspberry Pi（自動化）"]
        S1["cron: 每週一 9am JST\nupdate_roster.py\nupdate_schedule.py\nupdate_stats.py"]
        S2["cron: 每小時 22:00–08:00 JST\nupdate_lineup.py"]
        S3["手動觸發\nadd_trade_target.py\n（加入觀察球員時）"]
    end

    subgraph Notion["Notion DB"]
        DB1[("DB1: Players\n所有球員\nMy Roster + Trade Target")]
        DB2[("DB2: Schedule\n每日賽況")]
        DB3[("DB3: Stats\n區間快照 7d/14d/30d/season")]
    end

    subgraph Views["Notion View（查閱用）"]
        V1["先發陣容 + 守備彈性"]
        V2["今日賽況（打線狀態）"]
        V3["本週對戰一覽"]
        V4["交易分析板"]
        V5["同位置比較"]
    end

    Y -->|roster / eligible_positions| S1
    Y -->|season stats| S1
    M -->|schedule / starter| S1
    M -->|lineups| S2
    Y -->|target player info| S3
    S1 -->|upsert| DB1
    S1 -->|建立當週 rows| DB2
    S1 -->|upsert 區間快照 x4| DB3
    S2 -->|更新 Lineup_Status| DB2
    S3 -->|upsert| DB1
    S3 -->|建立賽程 rows| DB2
    DB1 --> V1
    DB2 --> V2
    DB2 --> V3
    DB1 --> V4
    DB3 --> V4
    DB1 --> V5
    DB3 --> V5
    DB1 -.->|Relation| DB2
    DB1 -.->|Relation| DB3
```

---

## DB 設計

### DB1：Players（所有球員）

自己的陣容 + 潛力交易目標統一放這裡，用 `Player_Type` 區分

更新時機：每週一自動 + 新增交易目標時手動觸發

| Property | 類型 | 說明 |
|----------|------|------|
| Name | Title | 球員姓名 |
| MLB_Team | Select | 所屬 MLB 球隊（TOR / LAD…） |
| Player_Type | Select | `My Roster` / `Trade Target` |
| Fantasy_Team | Text | 目前在哪支 Fantasy 隊（My Roster 留空） |
| Current_Slot | Select | Fantasy 位置（C/1B/2B/3B/SS/OF/Util/BN/IL），Trade Target 留空 |
| Eligible_Positions | Multi-select | 可守位置（C/1B/2B/3B/SS/OF/Util） |
| Position_Type | Select | B（打者）/ P（投手） |
| Status | Select | Healthy / DTD / IL |
| Notes | Text | 交易筆記、分析備忘 |
| Player_ID | Number | Yahoo player_id（upsert key） |

---

### DB2：Schedule（每日賽況）

自己的球員 + Trade Target 都有賽程，方便比較誰這週出賽多

每週一建立當週 7 天資料列，打線狀態每小時更新一次

| Property | 類型 | 說明 |
|----------|------|------|
| Title | Title | `姓名 YYYY-MM-DD`（upsert key） |
| Player | Relation → DB1 | 關聯球員 |
| Player_Type | Formula | 從 DB1 rollup，方便直接 filter |
| Date | Date | 比賽日期（ET 基準） |
| Opponent | Text | 對手球隊（`vs NYY` / `@ BOS`） |
| Opposing_SP | Text | 對手先發投手 |
| Lineup_Status | Select | 打者：`IN` 在打線 / `OUT` 未上場 / `TBD` 未公布 / `OFF` 休息日；投手：`START` 今日先發 / `TBD` 有賽非先發 / `OFF` 休息日 |
| Week | Number | Fantasy 週次 |

---

### DB3：Stats（區間快照數據）

每週一更新，每個球員每週存 3 筆（3 個時間窗），用來對比交易目標與自己球員的數據。
累積數據到中後期參考價值低，改用區間快照才能反映當下狀態與趨勢。
注意：Yahoo API 不支援 14d 區間（無 last14days 參數），已省略。

| Property | 類型 | 說明 |
|----------|------|------|
| Title | Title | `姓名 W{週次} {period}`（upsert key，例：`Altuve W15 7d`） |
| Player | Relation → DB1 | 關聯球員 |
| Week | Number | 更新的 Fantasy 週次 |
| Period | Select | `7d` / `30d` / `season` |
| Updated_At | Date | 資料更新時間 |
| **打者** | | |
| AVG | Number | 打擊率 |
| HR | Number | 全壘打 |
| RBI | Number | 打點 |
| R | Number | 得分 |
| SB | Number | 盜壘 |
| **投手** | | |
| W | Number | 勝投 |
| SV | Number | 救援 |
| K | Number | 三振 |
| ERA | Number | 防禦率 |
| WHIP | Number | WHIP |

**Period 使用場景：**
- `7d` → 當下熱度，決定本週誰先發
- `30d` → 過濾短期噪音，看真實水準
- `season` → 全季基準，做最終比較

**Yahoo API 對應：** `stat_type=lastweek` / `lastmonth` / `season`（不支援 14d）

---

## 腳本規劃

| 腳本 | 觸發 | 說明 |
|------|------|------|
| `update_roster.py` | 每週一 / 手動 | 從 Yahoo API 拉自己陣容，upsert DB1 |
| `update_schedule.py` | 每週一 | 建立 DB1 所有球員的當週 DB2 rows |
| `update_stats.py` | 每週一 | 從 Yahoo API 拉數據，upsert DB3 |
| `update_lineup.py` | 每小時 22–08 JST | 只更新 DB2 今日 Lineup_Status |
| `add_trade_target.py` | 手動 | 輸入球員姓名 → 查 Yahoo API → upsert DB1 + 建立 DB2 本週賽程 |

---

## Notion View 規劃

| View 名稱 | DB | 類型 | Filter / Sort |
|-----------|-----|------|---------------|
| 先發陣容 | DB1 | Table | Player_Type = My Roster，Current_Slot ≠ BN/IL |
| 板凳＋彈性 | DB1 | Table | Player_Type = My Roster，Current_Slot = BN |
| 傷兵追蹤 | DB1 | Table | Status ≠ Healthy |
| 今日賽況 | DB2 | Table | Date = Today，sort by Lineup_Status |
| 本週對戰 | DB2 | Calendar | 本週，by Date |
| 交易分析板 | DB1 | Table | Player_Type = Trade Target，顯示 Eligible_Positions + Notes |
| 同位置比較 | DB3 | Table | filter by Eligible_Positions，My Roster vs Trade Target 並列 |

---

## Cron 排程（RPi）

```
# 每週一 9:00 JST = 0:00 UTC
0 0 * * 1  cd ~/fantasy-baseball && python3 sync/update_roster.py && python3 sync/update_schedule.py && python3 sync/update_stats.py

# 每小時（22:00–08:00 JST = 13:00–23:00 UTC）打線狀態更新
0 13-23 * * *  cd ~/fantasy-baseball && python3 sync/update_lineup.py
```

---

## Notion 設定

| 項目 | 值 |
|------|-----|
| Workspace | 新 Workspace（第二個） |
| API Key | `~/.config/notion/api_key_new` |
| Parent page | `34048ad3-2a1c-80a0-bcaa-ca973c2d4100` |
| DB1 Players | `1eb4bb64-da35-4e9d-b740-f36c8569d3a6` |
| DB2 Schedule | `4bf3af3c-7095-493a-8746-5ad0fc9f147f` |
| DB3 Stats | `d3de639b-94af-44e3-9795-9ac965bb5419` |

詳細設定見 `notion_config.py`。

---

## 備註

- DB1 用 `Player_ID` 做 upsert key
- DB2 用 `Title`（姓名＋日期）做 upsert key
- DB3 用 `Title`（姓名＋週次＋period，例：`Altuve W15 7d`）做 upsert key
- Trade Target 的賽程跟自己球員完全相同結構，`add_trade_target.py` 加人後自動補齊本週賽程
- Yahoo token 存在 RPi 本機 `oauth2.json`，`yahoo_oauth` 自動 refresh
- Notion API key 存在 RPi 環境變數或 `.env`
