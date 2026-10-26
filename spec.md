# CNE WJ1 DCS 品控力風險智控平台 — 開發規格書 v2.0（qcm-system-v3）

> 規格驅動開發（SDD）：本文件是唯一事實來源。程式碼必須符合本文件；若實作時發現本文件有誤，先改本文件再改程式碼。
>
> 文件狀態：**已鎖定，可開工**（D-01~D-04 已決議，見 §11）
> 最後更新：2026-10-26
>
> v1.1 變更：新增 §2.5 偵測方式字典、§3 等級生命週期（維修驅動的等級升降）、§5 事件帳本資料模型。
> v1.3 變更（實作後回填）：修正 KPOV 筆數為 244、移除不存在的「未評估」計數、現況等級改為應用層推算、
> 修正「惡化中／已改善」的計數定義。
> **v1.4 變更（實作後回填，2026-10）**：資料來源改為 `數據庫-1008／1011.xlsx`（含 OP 人工站、客訴報表、PCN／ECN、
> 高風險項點檢）；IMPROVE 生效時間改用修護報表「改善時間」；新增期間篩選（天／週／月／年）、
> 象限圖「期初 → 現在」、站別柱狀圖、站別風險地圖、措施表、緊急措施分類、Level 3 點檢監控與拍照點檢、
> 客訴回饋清單與製程異常清單、側邊導覽；移除口徑切換。**新功能的規格集中在 §13**，
> 前面各節中被取代的條文以「⚠ v1.4」標註。
> **v2.0 變更（qcm-system-v3，2026-10-20）**：資料來源改為 `數據庫-1019.xlsx`（**只支援 1019 版，不再相容 1008／1011 測試**）；
> 修護報表與客訴報表新增**緊急措施**與 8D 區塊；措施表的緊急措施／長期措施改讀新欄位、措施層別一律讀 Excel（移除手動分類）；
> 8D 明細側欄；高風險項點檢改為 KPIV(x) 點檢內容與管控等級、「開線/班」每班一次；點檢紀錄不可刪除；
> 側邊導覽改名；總覽頁暫時拿掉整線 Layout；部署目標改為 Cloudflare（Containers＋R2，SQLite 由 Litestream 備份）。**v2.0 規格集中在 §14**，被取代的條文以「⚠ v2.0」標註。
> **v2.1 變更（2026-10-26，RBAC）**：新增登入（系統自建帳號＋JWT）與三種角色（最高權限管理者／廠管理者／一般使用者），
> 資料依廠（WJ1～WJ8）隔離；匯入檔名改為 `廠-產品廠-線別-數據庫-月日.xlsx`，同一個廠可有多條線、每條線各自保留生效資料；
> 部署目標為 VM 與 Zeabur（Cloudflare 程式共用，登入設定為選用 secret）。**規格集中在 §15**。
> **v2.2 變更（2026-10-26，總覽廣播）**：總覽頁頂端新增廣播列（Level 3 個數變化、當班點檢次數、站別等級提升）。**規格見 §16**。
> **v2.3 變更（2026-10-26，完成期限與清單篩選）**：製程風險管理、客訴案件管理移除關鍵字搜尋，改為發生時間／機種（客訴為客戶）／站別／KPOV／改善時間篩選；上方新增預計完成與逾期圓餅（逾期依 8D 預計 vs 實際完成，分 7 天內、7–14 天、14 天以上），逾期以紅色標示。**規格見 §17**。
> **v2.4 變更（2026-10-26，點檢看板趨勢）**：點檢看板站別卡片上方新增左右兩半：每日異常次數＋漏點檢數折線、KPIV 點檢內容異常分布圓餅。**規格見 §18**。

---

## 1. 目標與範圍

### 1.1 目標
將現行以 Power BI 建立的「品控力模型」轉為獨立 Web 系統。系統不只呈現靜態的品控力分佈，更要**追蹤每個 KPOV 的品控力隨不良事件與改善措施而升降的完整歷程**。

### 1.2 v1 範圍（In Scope）
- 品控力 2×2 象限圖（KPOV 數量分佈 + 全廠基準對比）
- 站別 / 線別篩選
- Level 0~3 KPOV 數量柱狀圖
- **等級生命週期**：維修報表驅動的等級惡化 / 改善追蹤（§3）
- **等級異動歷程查詢**
- Excel 上傳匯入（取代 Power Query）
- 匯入批次管理與歷史保留
- **v1.4 新增**（詳見 §13）：期間篩選、站別 Level 柱狀圖、客訴／製程柱狀圖、站別風險地圖、
  等級異動措施表與緊急措施分類、PCN／ECN 時間軸、Level 3 點檢監控、拍照點檢、客訴回饋清單、製程異常清單

### 1.3 v1 不做（Out of Scope）
- 告警事件次數統計（資料已具備，UI 未定義；等級異動趨勢圖已於 v1.4 實作）
- AR 設備管理與 AR 掃描點檢：程式保留，但以功能開關暫時關閉（§13.11）
- 使用者登入與權限
- 自動接源（SQL Server / Dataverse 排程同步）
- 系統內手動登記等級異動（v1 僅匯入觸發，見 D-04）

---

## 2. 核心計算規則：品控力等級

> **這是整個系統的心臟。以下規則已用 244 筆 KPOV 與 3 筆維修紀錄完整驗證。**

### 2.1 偵測度評分語意

`小y偵測度` 與 `大Y偵測度` 採 FMEA 式 1–10 分制，**分數越小 = 偵測能力越強**。

| 分數 | 語意 | 對應實務 |
|---|---|---|
| 1–5 | 偵測能力**高** | 100% 機測 |
| 6–10 | 偵測能力**低** | 人檢 / 機測（未證實可靠） |

**切點固定為 5 / 6 之間。** 雙重佐證：
1. `gemini-svg.svg` 座標軸刻度（軸端標 1，中軸兩側標 5 與 6，另一端標 10）。
2. §2.5 偵測方式字典中，≥6 的方式全是「人工檢測」「隨機稽查」「未建立」或「未證實可靠的機器偵測」，
   ≤5 則全是已證實可靠的自動化手段——與象限圖標註的「100%机测」vs「人检/机测(未证实可靠)」完全吻合。
   （註：分數 1 的「失效模式不會實際發生」屬於預防而非偵測，仍落在 ≤5 的「高」側。）

### 2.2 象限定義

軸向（依 `gemini-svg.svg`）：
- **X 軸 = 小y 偵測度**，向右為「高」（分數小）
- **Y 軸 = 大Y 偵測度**，向上為「高」（分數小）

```
       大Y 高 (≤5)
            ↑
  Level 2   │   Level 0
  #F3EA95   │   #BFFFDA
  y 人檢/未證實 │ y 100%機測
  Y 100%機測 │ Y 100%機測
────────────┼────────────→ 小y 高 (≤5)
  Level 3   │   Level 1
  #FFCCFF   │   #C5E9FF
  y 人檢/未證實 │ y 100%機測
  Y 人檢/未證實 │ Y 人檢/未證實
            │
       大Y 低 (≥6)
   ←小y 低 (≥6)
```

### 2.3 判定演算法（虛擬碼）

```
function computeLevel(smallY: int, bigY: int) -> 0|1|2|3|null:
    if smallY is null or bigY is null:
        return null            # 資料不完整，不計入任何象限
    yHigh = (smallY <= 5)      # 小y 偵測能力高
    YHigh = (bigY   <= 5)      # 大Y 偵測能力高
    if  yHigh and  YHigh: return 0
    if  yHigh and !YHigh: return 1
    if !yHigh and  YHigh: return 2
    if !yHigh and !YHigh: return 3
```

### 2.4 驗證結果（對現有 244 筆有效資料）

| 小y | 大Y | 演算結果 | 原始欄位 | 筆數 | 一致 |
|---|---|---|---|---|---|
| 1 | 1 | Level 0 | Level 0 | 148 | ✅ |
| 3 | 5 | Level 0 | Level 0 | 12 | ✅ |
| 3 | 7 | Level 1 | Level 1 | 73 | ✅ |
| 4 | 7 | Level 1 | Level 1 | 1 | ✅ |
| 5 | 7 | Level 1 | Level 1 | 8 | ✅ |
| 7 | 7 | Level 3 | Level 3 | 1 | ✅ |
| 7 | 7 | Level 3 | **Level 0** | 1 | ❌ 來源錯誤 |

**一致率 243 / 244。**

### 2.5 偵測方式字典（**新增，v1 必備**）

來源：`修護報表` 工作表第 27–28 欄（無表頭，實為停在該處的對照表，與左側維修紀錄無關）。

| 偵測方式 | 偵測度分數 | 偵測能力 |
|---|---|---|
| 未建立 | 10 | 低 |
| 隨機稽查 | 9 | 低 |
| 人工檢測(未證實可靠) | 8 | 低 |
| 機器偵測(未證實可靠) | 7 | 低 |
| 人工檢測(已證實可靠) | 6 | 低 |
| 機器偵測(已證實可靠) | 5 | 高 |
| 機器自動偵測(製程下游) | 4 | 高 |
| 機器自動偵測(站內) | 3 | 高 |
| 機器偵測可偵測出失效原因且預防失效模式發生 | 2 | 高 |
| 失效模式不會實際發生 | 1 | 高 |

**REQ-DICT-01** 此表匯入為 `dim_detection_method`，是「偵測方式 ↔ 分數」的唯一轉換來源。
**REQ-DICT-02** 維修報表的偵測方式欄位以**字串完全比對**（trim 後）查此表。查不到 → 該列匯入失敗並列入錯誤報告，**不得以 0 或 NULL 帶過**。
**REQ-DICT-03** UI 中凡需輸入或顯示偵測度之處，一律顯示偵測方式名稱，分數為輔（例：`機器偵測(已證實可靠) (5)`）。

### 2.6 等級嚴重度排序（**REQ-CALC-02**）

```
Level 0  <  Level 1  <  Level 2  <  Level 3
（品控力最佳）                    （品控力最差）
```

語意：`Level 2`（站內小y偵測失效）比 `Level 1`（下游大Y偵測失效）**更嚴重**，因為不良已能通過站內管制。

此排序用於：判斷等級異動是「惡化(escalate)」或「改善(de-escalate)」、UI 警示色、待辦清單排序。**它不影響象限圖的幾何位置**——象限位置永遠依 §2.2。

### 2.7 等級處理原則（**REQ-CALC-01**）
1. 系統一律以 §2.3 演算法**重算**等級，不直接採用 Excel 的 `品控力等級` 欄位。
2. 匯入時若演算結果與來源欄位不符，**以演算結果為準**，並標記 `level_mismatch = true`。
3. 匯入完成頁需列出所有不符列。
4. Level 2 在基準資料中無筆數屬正常，UI 仍須顯示該象限並標示 0。

---

## 3. 等級生命週期（**v1.1 核心新增**）

### 3.1 概念

品控力等級**不是 KPOV 的靜態屬性**，而是 `(KPOV 編號 × 設備代碼)` 這個組合的**時序狀態**。

> KPOV 編號會跨設備重複：37 個編號攤在 246 列，光是 `K00004`（浮鎖）就掛在 9 台設備上。
> 某台設備發生不良，只降該台的等級，**不連坐其他 8 台**。

### 3.2 三種口徑

| 口徑 | 定義 | 來源 |
|---|---|---|
| **基準 (baseline)** | KPOV 庫原始評分算出的等級 | `KPOV库-by 站` |
| **現況 (current)** | 套用所有已生效異動事件後的等級 | 基準 + 事件帳本 |
| **目標 (target)** | 最新一次改善措施宣告要達到的等級 | 最近一筆 IMPROVE 事件 |

**系統預設顯示「現況」**（REQ-UI-16）。

> ⚠ v1.4：三種口徑仍由後端計算（API 的 `view` 參數保留），但畫面已**移除口徑切換**。
> 象限圖改為同時顯示「期初 → 現在」（§13.4），Level 明細依現在 Level。

### 3.3 狀態轉移

```
        ┌──────────────┐
        │   基準狀態    │  KPOV 庫評分
        └──────┬───────┘
               │
     發生不良，維修報表填入「變化後」偵測方式
               ↓
        ┌──────────────┐
        │  DEGRADE 事件 │  等級依新分數重算
        └──────┬───────┘  （通常惡化，但雙軸各自重評，
               │            單軸可能反向——見 §3.5）
     完成改善措施，維修報表填入「提升後」偵測方式
               ↓
        ┌──────────────┐
        │  IMPROVE 事件 │  等級依新分數重算
        └──────────────┘
```

**現況等級 = 該 (KPOV, 設備) 最新一筆已生效事件的等級；無事件則為基準等級。**

### 3.4 事件產生規則（**REQ-LIFE-01 ~ 06**）

- **REQ-LIFE-01** 匯入 `修護報表` 時，每一列若 `設備ID` 與 `KPOV 编号` 皆有值，則產生事件。無此兩欄的列略過並列入報告。
- **REQ-LIFE-02** 若該列有填 `小y偵測方式(變化後)` 與 `大y偵測方式(變化後)` → 產生一筆 **DEGRADE** 事件，生效時間 = `測試時間`（不良被發現的時刻）。
- **REQ-LIFE-03** 若該列有填 `小y偵測方式(提升後)` 與 `大y偵測方式(提升後)` → 產生一筆 **IMPROVE** 事件。「提升後」視為**已完成的事實**，匯入即生效。
- **REQ-LIFE-04** IMPROVE 事件的生效時間 = 修護報表的 **`改善時間`** 欄（⚠ v1.4，取代原「改善生效日／匯入批次時間」；⚠ v2.0 補充下限規則見 REQ-V2-LIFE-01）：
  - 來源檔有 `改善時間` 欄、但該列未填 → **不產生 IMPROVE**，列入匯入報告；**不得以匯入時間代替**。
  - 只有完全沒有此欄的舊版檔案（如 `raw_data.xlsx`），才退回以匯入批次時間代替。
  - `改善時間` 晚於現在者為**預計改善**：事件照樣入帳，但現況等級要到該時間才採用（`build_states` 的 `as_of`）；
    畫面以虛線「預計」標記，逾期未到者標「預計・已逾期」。
  > ⚠ **不得使用 `修復時間`**。`修復時間` 是 touchup 的完工時間，不是「鎖付角度 DOE 優化」這類改善措施的生效時間。見 D-03。
  > `修復時間` 改作為措施表中「緊急措施時間」（§13.6）。
- **REQ-LIFE-05** 事件為**冪等**：同一批次重複匯入不得重複產生事件。以 `(維修序號, KPOV編號, 設備代碼, 事件類型)` 為自然鍵去重。
- **REQ-LIFE-06** 每筆事件都必須保存：變更前後的兩軸偵測方式與分數、變更前後的等級、事件類型、生效時間、來源維修紀錄 ID、改善措施文字。**帳本只增不改**，任何修正都以新事件表達。

### 3.5 已驗證案例（K00004 浮鎖 @ OT00420118）

| 階段 | 小y 偵測方式 | 小y | 大Y 偵測方式 | 大Y | 等級 | 判定 |
|---|---|---|---|---|---|---|
| 基準 | 機器自動偵測(站內) | 3 | 機器偵測(未證實可靠) | 7 | **Level 1** | — |
| DEGRADE | 機器偵測(未證實可靠) | 7 | 機器偵測(已證實可靠) | 5 | **Level 2** | 惡化 ↑ |
| IMPROVE | 機器偵測(已證實可靠) | 5 | 機器偵測(已證實可靠) | 5 | **Level 0** | 改善 ↓↓ |

判讀：不良逃出站內、在下游被攔截 → 證明站內 `小y` 偵測不可靠（3→7 惡化），同時證明下游 `大Y` 偵測確實有效（7→5 修正）。**兩軸各自重評，可以一升一降**，等級由重評後的象限位置決定，不是單軸加減。

### 3.6 異動判定（**REQ-LIFE-07**）

```
function classifyTransition(levelBefore, levelAfter):
    if levelAfter > levelBefore: return 'ESCALATED'   # 惡化（依 §2.6 排序）
    if levelAfter < levelBefore: return 'IMPROVED'    # 改善
    return 'UNCHANGED'                                # 換軸但同級
```
`UNCHANGED` 事件仍須入帳（兩軸分數確實變了），但不計入「惡化中」清單。

---

## 4. 資料來源與對應

> ⚠ v1.4：目前的來源檔為 `數據庫-1008.xlsx`／`數據庫-1011.xlsx`，工作表與匯入規則見 **§13.1**。
> 以下為 v1.0～v1.3 對 `raw_data.xlsx` 的描述，保留作為舊版檔案的相容規格（測試仍以它驗證 AC-1~15）。

來源檔：`raw_data.xlsx`（5 個工作表）

| 工作表 | 列數 | 角色 | v1 使用 |
|---|---|---|---|
| `KPOV库-by 站 `（結尾有空白） | 246 | **主事實表 / 基準等級** | ✅ |
| `修護報表` | 10 | **等級異動事件來源 + 偵測方式字典** | ✅ |
| `Dim_Equipment` | 132 | 設備維度 | ✅ |
| `7_8月設備告警(與品質相關)` | 17,069 | 告警事件明細 | 匯入，v1 不呈現 |
| `設備告警品質相關代碼庫` | 8 | 錯誤碼字典 | ✅ |
| `與品質相關設M-error庫` | 8 | **與上表內容完全相同** | ❌ 忽略 |

### 4.1 關聯鍵（已驗證）

```
fact_kpov.equipment_code       ──→ dim_equipment.equipment_code     ✅ 10/10
fact_alarm.equipment_code      ──→ dim_equipment.equipment_code     ✅ 38/38
fact_kpov.alarm_code           ──→ dim_error_code.error_code        ⚠ 246 筆僅 65 筆有值
level_event.(kpov_no,equip)    ──→ fact_kpov.(kpov_no,equipment_code) ✅ 3/3
修護報表偵測方式字串            ──→ dim_detection_method.method_name  ✅ 全數命中
```

KPOV 表欄位名為 `設備ID`，Dim_Equipment 為 `設備代碼`，**值域相同**，統一命名 `equipment_code`。

### 4.2 已知資料現況
- `屬性1` 全部為 `CTP`（244/244）。
- `站別` 共 10 個值，與 `設備ID` 呈 **1:1**，全部位於 `DCS-PM1` 線。
- `Dim_Equipment` 中 `DCS-PM2` 線存在孿生設備，**但無對應 KPOV**（見 D-01）。
- 來源檔第 246 列為空白列、第 247 列是殘留公式 `=COUNTA(UNIQUE(L2:L245))`，兩列皆非資料，匯入時略過。
  因此**有效 KPOV 為 244 筆，且沒有「未評估」的 KPOV**。
- `KPOV 编号` 37 個唯一值，26 個跨設備重複。

---

## 5. 資料模型（PostgreSQL）

### 5.1 匯入批次與維度

```sql
CREATE TABLE import_batch (
  id          BIGSERIAL PRIMARY KEY,
  filename    TEXT NOT NULL,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  imported_by TEXT,
  row_counts  JSONB NOT NULL,
  status      TEXT NOT NULL,          -- pending|success|failed
  error_log   JSONB,
  is_active   BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE dim_detection_method (
  batch_id    BIGINT REFERENCES import_batch(id) ON DELETE CASCADE,
  method_name TEXT NOT NULL,
  score       SMALLINT NOT NULL CHECK (score BETWEEN 1 AND 10),
  PRIMARY KEY (batch_id, method_name)
);

CREATE TABLE dim_equipment (
  batch_id        BIGINT REFERENCES import_batch(id) ON DELETE CASCADE,
  equipment_key   TEXT,
  production_area TEXT,
  line            TEXT,
  model_code      TEXT,
  model_desc      TEXT,
  equipment_code  TEXT NOT NULL,
  equipment_desc  TEXT,
  PRIMARY KEY (batch_id, equipment_code)
);

CREATE TABLE dim_error_code (
  batch_id       BIGINT REFERENCES import_batch(id) ON DELETE CASCADE,
  error_code     TEXT NOT NULL,
  alert_category TEXT, error_content TEXT,
  breakdown_zh   TEXT, breakdown_en  TEXT,
  module_name    TEXT, io_signal     TEXT, component_code TEXT,
  PRIMARY KEY (batch_id, error_code)
);
```

### 5.2 KPOV 基準

```sql
CREATE TABLE fact_kpov (
  id               BIGSERIAL PRIMARY KEY,
  batch_id         BIGINT NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,
  spu_seq TEXT, spu_edms TEXT,
  process_category TEXT, process_nature TEXT,
  attribute TEXT, attribute1 TEXT,
  process_unit_zh TEXT, process_unit_en TEXT,
  station          TEXT NOT NULL,
  category         TEXT,
  kpov_name        TEXT NOT NULL,
  kpov_no          TEXT,
  alarm_code       TEXT,
  equipment_code   TEXT NOT NULL,
  small_y_score    SMALLINT,
  big_y_score      SMALLINT,
  cc_sc_reason     TEXT,
  level_source     TEXT,
  level_baseline   SMALLINT,   -- 0|1|2|3|NULL ← §2.3 算出的基準等級
  level_mismatch   BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX ON fact_kpov (batch_id, kpov_no, equipment_code);
CREATE INDEX ON fact_kpov (batch_id, station, level_baseline);
```

### 5.3 等級異動帳本（**核心新增**）

```sql
CREATE TYPE level_event_type AS ENUM ('DEGRADE', 'IMPROVE');
CREATE TYPE level_transition AS ENUM ('ESCALATED', 'IMPROVED', 'UNCHANGED');

CREATE TABLE fact_level_event (
  id              BIGSERIAL PRIMARY KEY,
  batch_id        BIGINT NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,

  -- 作用對象：KPOV × 設備
  kpov_no         TEXT NOT NULL,
  equipment_code  TEXT NOT NULL,

  event_type      level_event_type NOT NULL,
  effective_at    TIMESTAMPTZ NOT NULL,

  -- 變更前（前一筆事件的 after；無前筆則為 fact_kpov 基準）
  small_y_method_before TEXT, small_y_score_before SMALLINT,
  big_y_method_before   TEXT, big_y_score_before   SMALLINT,
  level_before          SMALLINT,

  -- 變更後
  small_y_method_after  TEXT NOT NULL, small_y_score_after SMALLINT NOT NULL,
  big_y_method_after    TEXT NOT NULL, big_y_score_after   SMALLINT NOT NULL,
  level_after           SMALLINT NOT NULL,

  transition      level_transition NOT NULL,

  -- 溯源
  repair_id       BIGINT REFERENCES fact_repair(id),
  repair_serial   TEXT,              -- 維修序號，冪等鍵之一
  defect_desc     TEXT,              -- 不良描述
  improvement     TEXT,              -- 改善措施
  note            TEXT
);
CREATE UNIQUE INDEX ON fact_level_event
  (batch_id, repair_serial, kpov_no, equipment_code, event_type);   -- REQ-LIFE-05 冪等
CREATE INDEX ON fact_level_event (batch_id, kpov_no, equipment_code, effective_at DESC);
```

### 5.4 現況等級視圖

> ⚠ **實作採用應用層推算，不建此 view。** 下列 SQL 使用 PostgreSQL 專有的 `LATERAL` join，
> SQLite 不支援，會讓開發環境與正式環境行為分歧。實際實作在 `services/lifecycle.py`，
> 邏輯與此 view 等價且兩種資料庫一致。此段保留作為語意定義。

```sql
CREATE VIEW v_kpov_current AS
SELECT
  k.*,
  COALESCE(e.level_after,          k.level_baseline)   AS level_current,
  COALESCE(e.small_y_score_after,  k.small_y_score)    AS small_y_current,
  COALESCE(e.big_y_score_after,    k.big_y_score)      AS big_y_current,
  e.id            AS last_event_id,
  e.event_type    AS last_event_type,
  e.effective_at  AS last_event_at,
  (e.id IS NOT NULL AND e.level_after <> k.level_baseline) AS deviates_from_baseline
FROM fact_kpov k
LEFT JOIN LATERAL (
  SELECT * FROM fact_level_event ev
  WHERE ev.batch_id = k.batch_id
    AND ev.kpov_no = k.kpov_no
    AND ev.equipment_code = k.equipment_code
    AND ev.effective_at <= now()
  ORDER BY ev.effective_at DESC, ev.id DESC
  LIMIT 1
) e ON true;
```

### 5.5 其餘事實表

```sql
CREATE TABLE fact_alarm (
  id BIGSERIAL PRIMARY KEY,
  batch_id BIGINT NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,
  period TEXT, region TEXT, site TEXT, production_area TEXT, line TEXT,
  model_code TEXT, model_desc TEXT, model_desc_en TEXT,
  product_category TEXT, process_unit TEXT, shared_equipment TEXT,
  equipment_code TEXT NOT NULL, equipment_desc TEXT,
  prev_start_at TIMESTAMPTZ, stop_start_at TIMESTAMPTZ, stop_end_at TIMESTAMPTZ,
  tbs_min NUMERIC(12,2), downtime_min NUMERIC(12,2),
  stop_code TEXT, stop_duration_min NUMERIC(12,2),
  breakdown_desc TEXT, alarm_subcategory TEXT, alarm_content TEXT
);
CREATE INDEX ON fact_alarm (batch_id, equipment_code, stop_start_at);

CREATE TABLE fact_repair (
  id BIGSERIAL PRIMARY KEY,
  batch_id BIGINT NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,
  month TEXT, serial_no TEXT, product_model TEXT, work_order TEXT,
  line TEXT, team TEXT, tested_at TIMESTAMPTZ,
  defect_desc TEXT, product_defect_desc TEXT, repair_part_location TEXT,
  responsibility TEXT, defect_cause TEXT, sub_category TEXT,
  technician TEXT, repaired_at TIMESTAMPTZ, countermeasure TEXT,
  responsible_dept TEXT, remark TEXT,
  equipment_code TEXT, kpov_no TEXT,
  small_y_method_after TEXT, big_y_method_after TEXT,      -- 「變化後」
  improvement TEXT,
  small_y_method_improved TEXT, big_y_method_improved TEXT, -- 「提升後」
  improvement_effective_at TIMESTAMPTZ                      -- 來源新增欄位，可為 NULL
);
```

**版本策略**：每次匯入建立新 `import_batch`，成功後單一交易內切換 `is_active`。查詢預設讀 active 批次，舊批次保留可回溯。

---

## 6. 匯入規格

- **REQ-IMP-01** 接受 `.xlsx`。工作表以名稱 trim 後前綴比對（`KPOV库-by 站 ` 結尾有空白）。
- **REQ-IMP-02** 欄位以表頭名稱對應。表頭需 `strip()` 並移除 `_x000D_`、換行符。
- **REQ-IMP-03** 缺必要工作表 / 欄位 → 整批 rollback，回報缺哪張表、哪個欄位。
- **REQ-IMP-04** `與品質相關設M-error庫` 忽略；若與 `設備告警品質相關代碼庫` 內容不一致則報警告。
- **REQ-IMP-05** `修護報表` 第 27–28 欄為偵測方式字典（§2.5），**須與左側維修紀錄分開解析**：從第 27 欄往下讀至空白列為止。維修紀錄只解析第 0–24 欄。
- **REQ-IMP-06** 偵測度欄位轉 int；空值存 NULL，不視為 0。
- **REQ-IMP-07** 匯入順序（有相依）：
  `dim_detection_method` → `dim_equipment` / `dim_error_code` → `fact_kpov`（算 baseline）→ `fact_repair` → `fact_level_event`（依 §3.4 推導，需回查 fact_kpov 取 before 值）
- **REQ-IMP-08** 匯入完成頁回報：各表筆數、等級不符列、關聯鍵未命中列、偵測方式查無字典的列、產生的等級異動事件清單（含 ESCALATED / IMPROVED 統計）。
- **REQ-IMP-09** 匯入為單一交易；失敗不留半套資料。

---

## 7. API 規格

Base: `/api/v1`。所有統計端點共用參數 `view=current|baseline|target`（預設 `current`）、`station`、`line`、`attribute`、`target`（Layout 熱區選取）（多值者以逗號分隔）。

> ⚠ v1.4：新增端點與期間參數 `window=day|week|month|year` 見 **§13.12**；`/quadrant` 的新欄位 `start` 見 §13.4。

### `GET /filters`
```json
{
  "stations": [{"code":"鎖銅排","equipmentCode":"OT00420118","kpovCount":26}],
  "lines": [{"code":"DCS-PM1","label":"DCS-PM1"}],
  "batch": {"id":12,"filename":"raw_data.xlsx","importedAt":"2026-09-21T12:56:00Z"}
}
```

### `GET /quadrant?view=&station=&line=`
```json
{
  "view": "current",
  "scope":    {"level0":161,"level1":81,"level2":0,"level3":2,"unrated":2,"total":246},
  "plant":    {"level0":161,"level1":81,"level2":0,"level3":2,"unrated":2,"total":246},
  "baseline": {"level0":160,"level1":82,"level2":0,"level3":2,"unrated":2,"total":246},
  "filtered": false,
  "deviationCount": 3
}
```
- `scope` = 套用篩選後的數字
- `plant` = 全廠基準對比（永遠未篩選的全量，同 view）
- `baseline` = 同篩選範圍的基準口徑，供「現況 vs 基準」對照
- `deviationCount` = 現況與基準不同的 KPOV×設備 組合數

### `GET /levels/bar?view=&station=&line=`
口徑為 **KPOV 項目數**。
```json
{
  "bars": [
    {"level":0,"count":161,"baselineCount":160,"color":"#BFFFDA"},
    {"level":1,"count":81, "baselineCount":82, "color":"#C5E9FF"},
    {"level":2,"count":0,  "baselineCount":0,  "color":"#F3EA95"},
    {"level":3,"count":2,  "baselineCount":2,  "color":"#FFCCFF"}
  ],
  "unrated": 2
}
```

### `GET /kpov?view=&station=&line=&level=&deviatedOnly=`
KPOV 明細（分頁）。每列含 `levelBaseline`、`levelCurrent`、`lastEventAt`、`transition`。

### `GET /kpov/{kpovNo}/{equipmentCode}/history`
單一 KPOV×設備 的完整等級歷程（時間軸）。
```json
{
  "kpovNo":"K00004","kpovName":"浮鎖","equipmentCode":"OT00420118","station":"鎖銅排",
  "baseline": {"smallY":{"method":"機器自動偵測(站內)","score":3},
               "bigY":{"method":"機器偵測(未證實可靠)","score":7},"level":1},
  "events": [
    {"type":"DEGRADE","effectiveAt":"2025-11-17T08:44:48Z","transition":"ESCALATED",
     "levelBefore":1,"levelAfter":2,
     "smallY":{"method":"機器偵測(未證實可靠)","score":7},
     "bigY":{"method":"機器偵測(已證實可靠)","score":5},
     "defectDesc":"螺絲浮鎖/高翹","repairSerial":"ALG25B01310WB"},
    {"type":"IMPROVE","effectiveAt":"2026-09-21T12:56:00Z","transition":"IMPROVED",
     "levelBefore":2,"levelAfter":0,
     "smallY":{"method":"機器偵測(已證實可靠)","score":5},
     "bigY":{"method":"機器偵測(已證實可靠)","score":5},
     "improvement":"鎖付角度DOE優化，得出最佳參數保護"}
  ],
  "current": {"level":0}
}
```

### `GET /events?station=&line=&transition=&from=&to=`
等級異動事件列表，供「異動總覽」頁。

### `POST /import` / `GET /import/history`
匯入與批次歷史。

---

## 8. 畫面規格

> ⚠ v1.4：首頁版面、象限圖數字、柱狀圖與篩選器皆已更新，現行規格見 **§13.3～§13.11**。
> 本節保留未被取代的條文（REQ-UI-01~03、05、06、13~15、18~21）；被取代者逐條標註。

### 8.1 版面（⚠ v1.4 已由 §13.3 取代）

```
┌─────────────────────────────────────────────────────────────┐
│  品質管控力            口徑：[現況 ▾]           [匯入資料]   │
├──────────────────────────────┬──────────────────────────────┤
│  品控力象限圖 (2×2 SVG)       │  等級異動總覽                │
│  700×550 viewBox, 自適應      │  ↑惡化中 N  ↓已改善 M        │
│                              │  最近異動清單（可點擊）       │
├──────────────────────────────┴──────────────────────────────┤
│  CTP 站別：[ 全部 ▾ ]     線別：[ 全部 ▾ ]        [清除篩選] │
├─────────────────────────────────────────────────────────────┤
│  Level 0~3 KPOV 數量                                         │
│  ▇▇▇▇▇▇▇▇▇▇ 柱狀圖（虛線疊基準）                             │
│  ■ Level 0  ■ Level 1  ■ Level 2  ■ Level 3                 │
└─────────────────────────────────────────────────────────────┘
```

> 原「右欄預留空白」現指派給**等級異動總覽**（原 D-03 解除）。

### 8.2 象限圖（REQ-UI-01 ~ 06）

- **REQ-UI-01** 以 `gemini-svg.svg` 為視覺基準：座標軸、箭頭、軸標籤、刻度數字 1/5/6/10 全部保留。
- **REQ-UI-02** 四象限位置與配色固定：

  | 象限 | 位置 | 等級 | 色碼 |
  |---|---|---|---|
  | 右上 | 小y高·大Y高 | Level 0 | `#BFFFDA` |
  | 右下 | 小y高·大Y低 | Level 1 | `#C5E9FF` |
  | 左上 | 小y低·大Y高 | Level 2 | `#F3EA95` |
  | 左下 | 小y低·大Y低 | Level 3 | `#FFCCFF` |

- **REQ-UI-03** 每格顯示：Level 標籤 + KPOV 數量（大字）+ 佔比 + 原 SVG 的兩行偵測方式說明。
- **REQ-UI-04** 象限圖跟隨篩選器連動。有套用篩選時，每格在大數字下方以淡灰小字顯示全廠基準：`全廠 160`。
- **REQ-UI-05** 點擊任一象限 → 側邊面板列出該象限 KPOV 明細（站別、KPOV、編號、設備、小y/大Y 偵測方式與分數、基準等級、現況等級）。
- **REQ-UI-06** 數量為 0 的象限仍完整繪製並顯示 `0`。

### 8.3 等級生命週期呈現（**REQ-UI-16 ~ 21**）

- ~~**REQ-UI-16** 頁首「口徑」切換：`現況` / `基準` / `目標`，預設現況。~~ ⚠ v1.4 移除，見 §13.4。
- **REQ-UI-17** ⚠ v1.4 修訂：象限每格的增減（`▲+1` / `▼-1` / `持平`）改為「現在 − 期初」，顯示在大數字**下方**
  （原本放在角落會壓到刻度數字），顏色規則不變：Level 0 增加為綠，其他格增加為紅。
- **REQ-UI-18** 右欄「等級異動總覽」顯示：
  - 兩個計數卡：**惡化中**（現況等級比基準嚴重）、**已改善**（現況等級優於基準）。
    刻意比對「現況 vs 基準」而非最後一筆事件的 transition：同一 (KPOV, 設備) 若有多張維修單
    宣告同一項改善，最後一筆會是 UNCHANGED，但該 KPOV 相對基準確實已改善。
  - 最近異動清單，每列：`KPOV 名稱 · 設備 · Level X → Level Y · 日期`，等級變化以箭頭與顏色標示
  - 點擊任一列 → 開啟該 KPOV×設備 的歷程時間軸
- **REQ-UI-19** 歷程時間軸（側邊面板）：垂直時間線，依序顯示基準 → 各事件 → 現況。每個節點顯示兩軸偵測方式變化（`機器自動偵測(站內) (3) → 機器偵測(未證實可靠) (7)`）、等級變化、不良描述或改善措施、來源維修序號。
- **REQ-UI-20** 「惡化中」計數 > 0 時，該計數卡以警示色呈現，作為待辦提示。
- **REQ-UI-21** KPOV 明細列表中，現況等級與基準不同的列以左側色條標記，並提供 `僅顯示有異動` 篩選開關。

### 8.4 篩選器（REQ-UI-07 ~ 09）
- **REQ-UI-07** ⚠ v1.4 修訂：三個多選下拉 `線別`、`屬性`（CTP 自動站／OP 人工站）、`站別`，旁邊為 `期間` 分段按鈕（§13.2）。**不設「選擇設備」下拉**。
- **REQ-UI-08** 皆多選，預設「全部」，各條件為 AND。
- **REQ-UI-09** 篩選狀態、期間與 Layout 選取皆同步到 URL query string（`line`、`attribute`、`station`、`window`、`target`、`deviatedOnly`）；預設值不寫入網址。

### 8.5 柱狀圖（REQ-UI-10 ~ 12）（⚠ v1.4：首頁改為三張站別 × Level 柱狀圖，見 §13.5；象限圖下方保留 Level 0~3 計數列）
- **REQ-UI-10** X 軸固定四根柱，數量為 0 仍保留柱位。
- **REQ-UI-11** 柱體顏色同 8.2。柱頂標數值。現況口徑下，以虛線水平標記疊上基準值供對照。
- **REQ-UI-12** 有未評估 KPOV 時於圖下註記 `另有 N 筆 KPOV 未評估偵測度`，不畫成第五根柱。

### 8.6 通用
- **REQ-UI-13** 繁體中文介面；資料值照原樣顯示（來源含簡體，不轉換）。
- **REQ-UI-14** 頁尾顯示當前資料批次：檔名 + 匯入時間。
- **REQ-UI-15** 載入中 / 無資料 / 錯誤三種狀態皆須有明確畫面。

---

## 9. 驗收條件

| # | 條件 |
|---|---|
| AC-1 | 上傳 `raw_data.xlsx` 匯入成功：KPOV **244**、告警 17,069、設備 132、錯誤碼 8、偵測方式字典 10、維修紀錄 3 |
| AC-2 | 匯入報告列出 1 筆等級不符（小y=7, 大Y=7 標為 Level 0） |
| AC-3 | 基準口徑無篩選：L0=160、L1=82、L2=0、L3=2，未評估 0，合計 244 |
| AC-4 | 柱狀圖四根柱皆存在，Level 2 柱高 0 但柱位保留 |
| AC-5 | 選擇站別「鎖銅排」後，象限圖數字變動且每格出現全廠基準小字 |
| AC-6 | 點擊 Level 1 象限，側邊面板列出對應筆數的 KPOV |
| AC-7 | 篩選與口徑切換後重新整理頁面，條件保留 |
| AC-8 | 格式錯誤的檔案回傳明確錯誤且資料庫無殘留 |
| AC-9 | 四象限色碼與 `gemini-svg.svg` 逐字相符 |
| **AC-10** | 匯入產生 **6 筆**等級異動事件（3 筆維修紀錄 × DEGRADE + IMPROVE） |
| **AC-11** | K00004 @ OT00420118 歷程為：基準 L1 → DEGRADE L2（ESCALATED）→ IMPROVE L0（IMPROVED） |
| **AC-12** | K00004 的其餘 7 台設備（未出現在維修報表）現況等級**仍為 L1**，未被連坐 |
| **AC-13** | 口徑切「基準」與「現況」，象限數字不同；切回結果一致 |
| **AC-14** | 同一檔案重複匯入兩次，等級異動事件數仍為 6（冪等，REQ-LIFE-05） |
| **AC-15** | 偵測方式字串改為字典中不存在的值，該列匯入失敗並出現在錯誤報告，不以 0 帶過 |

> AC-1~15 以 `raw_data.xlsx` 驗證。v1.4 對 `數據庫-1011.xlsx` 的驗收條件：

| # | 條件 |
|---|---|
| **AC-16** | 匯入 1011：KPOV 331 筆（CTP 244、OP 87），18 個設備；OP 站設備代碼 A0001–A0008 依 §13.1 補上 |
| **AC-17** | 象限圖無期間時 `start` 為 null；任一期間 `scope.total = start.total = 331`；期初分佈與逐筆以 history 推算的結果一致 |
| **AC-18** | 選「年」時期初分佈等於 KPOV 原始 Level（L0=165、L1=126、L2=33、L3=7） |
| **AC-19** | 站別 Level 分佈圖 18 站、各 Level 加總等於象限圖基準口徑的數字 |
| **AC-20** | 客訴／製程柱狀圖：期間內維修筆數（含算不出 Level 者）等於站別風險地圖的維修筆數；序號 1 的客訴計在 OT00420118 的 Level 3；未填設備ID 的 7 筆列為 `unmappedComplaints` |
| **AC-21** | `改善時間` 未填的維修列不產生 IMPROVE；改善時間在未來者為預計改善，不計入現況與「已改善」 |
| **AC-22** | 重新匯入後，已儲存的緊急措施分類仍在（自然鍵，不掛批次） |

---

## 10. 技術選型

| 層 | 選擇 | 理由 |
|---|---|---|
| 前端 | React 19 + TypeScript + Vite + react-router | 象限圖用手寫 inline SVG（版面固定，不需圖表庫） |
| 圖表 | 象限圖：inline SVG；柱狀圖：Recharts | |
| 樣式 | Tailwind CSS | |
| 後端 | Python 3.12 + FastAPI + Pydantic | 與 openpyxl 同生態，Excel 處理最順 |
| ORM | SQLAlchemy 2.0 | 欄位增補以 `app/migrations.py` 的 `ADDED_COLUMNS` 於啟動時補上（v1.4） |
| DB | 開發：SQLite；正式：PostgreSQL | 現況等級改在應用層推算（§5.4），兩者行為一致 |
| 部署 | Linux VM：Docker Compose（`DEPLOY.vm.md`）；雲端：Zeabur（`DEPLOY.zeabur.md`） | 見 §10.3 |

測試一律使用暫存資料庫（`backend/tests/conftest.py` 在收集測試前設定 `QCM_DATABASE_URL`），
不得連到開發用的 `backend/data/qcm.db`。

### 10.1 專案結構
```
QualityControlModeling/
├── spec.md                      ← 本文件
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py            # §5
│   │   ├── schemas.py           # §7
│   │   ├── importer/
│   │   │   ├── excel.py         # §6
│   │   │   ├── mapping.py       # 工作表/欄位名對應
│   │   │   └── level_events.py  # §3.4 事件推導
│   │   ├── services/
│   │   │   ├── level.py         # §2.3 判定（唯一實作處）
│   │   │   └── lifecycle.py     # §3.6 異動分類、現況推算
│   │   └── api/v1/
│   ├── alembic/
│   └── tests/
│       ├── test_level.py        # §2.4 表格逐列測試
│       └── test_lifecycle.py    # §3.5 K00004 案例端到端測試
└── frontend/
    ├── src/
    │   ├── components/
    │   │   ├── QuadrantChart.tsx
    │   │   ├── LevelBarChart.tsx
    │   │   ├── FilterBar.tsx
    │   │   ├── ViewToggle.tsx        # 現況/基準/目標
    │   │   ├── DeviationPanel.tsx    # 等級異動總覽
    │   │   └── LevelTimeline.tsx     # 歷程時間軸
    │   ├── api/
    │   └── constants.ts         # LEVEL_COLORS / LEVEL_SEVERITY 單一來源
    └── ...
```

### 10.3 部署（REQ-DEP-01 ~ 06）

- **REQ-DEP-01** 三個容器：`db`（postgres:16-alpine）、`api`（`backend/Dockerfile`）、`web`（`frontend/Dockerfile`，nginx 提供靜態頁並把 `/api/` 反向代理到 `api`）。只有 `web` 對外開 port（`WEB_PORT`，預設 8080）。
- **REQ-DEP-02** 設定集中在 `.env`（範本 `.env.example`，不進版控）；`POSTGRES_PASSWORD` 必填，未設定時 compose 直接報錯。
- **REQ-DEP-03** 資料持久化：資料庫在 volume `pgdata`；拍照點檢照片與 AR 圖檔在 `apidata`（`QCM_DATA_DIR=/app/data`）。
- **REQ-DEP-04** 三個服務皆 `restart: unless-stopped` 並有健康檢查（db：`pg_isready`；api：`/health`；web：首頁），依序等待前一個 healthy 才啟動。
- **REQ-DEP-05** `api` 的後端程序以非 root（uid 10001）執行，且只能單一程序（線上人數存在程序記憶體）。
  容器以 root 啟動，`docker-entrypoint.sh` 先把 `QCM_DATA_DIR` 的擁有者改成 app，再以 `setpriv` 降權——
  平台掛上的 volume（Zeabur、compose）多半屬於 root，直接以非 root 啟動會無法寫入照片。
  Zeabur 的 api 服務 volume 須掛在 `/app/data`（與 `QCM_DATA_DIR` 預設一致）。
- **REQ-DEP-06** VM 不能連外網時，以 `docker save` 打包 `qcm-api`、`qcm-web`、`postgres:16-alpine` 成 `qcm-images.tar.gz`，VM 上 `docker load` 後 `docker compose up -d --no-build`，不需原始碼（步驟見 `DEPLOY.vm.md`）。

### 10.2 開發順序
1. DB schema + Alembic migration
2. `services/level.py` + 單元測試（§2.4 為測資）← **先做這個**
3. `services/lifecycle.py` + 單元測試（§3.5 K00004 為測資）
4. Excel importer（含字典解析 REQ-IMP-05）+ 對 `raw_data.xlsx` 整合測試
5. 事件推導 `level_events.py` + 冪等測試（AC-14）
6. API
7. 前端象限圖（先切版對齊 SVG，再接資料）
8. 前端柱狀圖 + 篩選器 + 口徑切換
9. 異動總覽 + 歷程時間軸
10. 匯入頁面
11. Docker Compose 打包

---

## 11. 決議事項（2026-09-21 確認，規格已鎖定）

| # | 問題 | **決議** |
|---|---|---|
| **D-01** | KPOV 只建在 DCS-PM1。篩選 DCS-PM2 時顯示什麼？ | ✅ KPOV 定義綁「站別」不綁「線別」。選 PM2 時同站別 KPOV 照樣顯示，畫面標註「KPOV 定義繼承自 DCS-PM1」。 |
| **D-02** | 匯入權限：誰能上傳？ | ✅ v1 不做登入、不做權限控管。 |
| **D-03** | 改善措施的生效日沒有欄位可放。 | ✅ 以**匯入批次時間**為 IMPROVE 生效時間；`fact_repair.improvement_effective_at` 欄位預留，來源 Excel 一加上 `改善生效日` 即自動優先採用（REQ-LIFE-04）。 |
| **D-04** | 是否需要在系統內手動登記等級異動（不經 Excel）？ | ✅ v1 不做，僅匯入觸發。資料模型已支援（`fact_level_event.repair_id` 可為 NULL），v2 加表單即可。 |

### 11.1 D-01 實作細則（**REQ-LINE-01 ~ 03**）
- **REQ-LINE-01** KPOV 的歸屬維度是 `station`。線別篩選時，取該線別在 `dim_equipment` 中的所有設備 → 反查其 `station` → 顯示這些站別的 KPOV。
- **REQ-LINE-02** 若某設備的站別有 KPOV 定義、但該設備本身在 `fact_kpov` 中無列（如 DCS-PM2 的孿生設備），視為**繼承**該站別的 KPOV 定義，並在 API 回應中標記 `inherited: true`、來源線別 `inheritedFrom: "DCS-PM1"`。
- **REQ-LINE-03** UI 於篩選列下方顯示提示條：`DCS-PM2 的 KPOV 定義繼承自 DCS-PM1`。繼承而來的 KPOV **不產生獨立的等級異動狀態**——等級異動仍只綁實際出現在維修報表中的 `(KPOV, 設備)` 組合。

## 12. 已知資料問題（請於來源端修正）

1. KPOV 庫有 1 筆 `小y=7, 大Y=7` 被標為 `Level 0`，應為 `Level 3`。
2. KPOV 庫第 246 列為空白列、第 247 列殘留公式 `=COUNTA(UNIQUE(L2:L245))`，建議刪除，以免日後被誤當資料。
3. `與品質相關設M-error庫` 與 `設備告警品質相關代碼庫` 內容完全重複，建議刪除其一。
4. `修護報表` 的偵測方式字典停在第 27–28 欄且無表頭，容易被誤當成資料欄。**建議移到獨立工作表**（例如 `Dim_偵測方式`）並補上表頭，匯入程式會更穩固。
5. `修護報表` 缺少 `改善生效日` 欄位（見 D-03）。
6. `設備告警代碼` 在 246 筆 KPOV 中僅 65 筆有值，其餘 KPOV 無法與告警事件關聯——這會限制未來「告警次數」口徑的覆蓋率。

v1.4（`數據庫-1011.xlsx`）：

7. `客訴報表` 8 筆中只有序號 1 填了 `設備ID`／`KPOV 編號`，其餘 7 筆無法歸到站別與 KPOV
   （畫面以「未對應 KPOV」及 `unmappedComplaints` 標示）。
8. 修護報表中鎖後蓋的 `K00051 @ A0003` 不在 KPOV 庫，無法產生等級事件，柱狀圖列為「算不出 Level」。
9. `K00056`（理線不良）改善後反而由 L2 變 L3，疑似「提升後」偵測方式填錯。
10. 1011 版移除了「設備對應參考」的 OP 區，且自動3／自動4 站位對調；系統以內建對照補足（§13.1）。
11. `KPOV-by 站` 工作表存檔時帶著自動篩選（只顯示 16 列），容易誤判資料筆數。

---

## 13. v1.4 功能規格（2026-10 實作後回填）

### 13.1 資料來源與匯入（REQ-IMP-10 ~ 17）

來源檔：`數據庫-1008.xlsx`／`數據庫-1011.xlsx`。工作表以名稱前綴比對（`importer/mapping.py` 的 `SHEET_PREFIXES`）：

| 工作表 | 角色 |
|---|---|
| `KPOV-by 站`（舊名 `KPOV库-by 站`） | KPOV 基準。1011 版 331 筆：CTP 自動站 244、OP 人工站 87 |
| `修護報表` | 維修紀錄＋偵測方式字典；新增 `改善時間`、`長期措施` 欄 |
| `設備對應參考` | 取代 `Dim_Equipment`，含 OP 人工站設備 |
| `客訴報表` | 客訴（8D），§13.10 |
| `PCN 紀錄`／`ECN 紀錄` | 變更紀錄，只供時間軸顯示（§13.8） |
| `高風險項點檢` | Level 3 點檢項目（§13.9） |
| `鎖附設備告警`／`塗覆設備告警` | 告警明細（匯入，不呈現） |

- **REQ-IMP-10** 只有 `修護報表` 每次必須提供。其他工作表未提供（不存在或完全空白）時，**沿用目前生效批次**的資料複製到新批次，並在匯入報告列出警告。首次匯入時 KPOV 庫與設備對應仍為必要。
- **REQ-IMP-11** 維修紀錄跨批次累積：以（序號, KPOV 編號, 設備ID）比對前一批次——內容相同略過、內容有變（例如補上改善）以新版取代、新的新增；這次檔案沒有的舊紀錄保留。等級事件以合併後的全部紀錄重新推導。
- **REQ-IMP-12** OP 人工站設備代碼：修護報表中沒有設備ID 的列即 OP 站。對照以檔案中的「設備對應參考」OP 區為準；1011 版移除該區，故內建預設 `DEFAULT_OP_EQUIPMENT`：
  人工一 插線/理線 A0001、人工二 固定散熱片 A0002、人工三 鎖後蓋 A0003、人工四 固定銅排/ 電感 A0004、
  人工五 固定保險絲/軟銅排 A0005、人工六 軟銅排1 A0006、人工七 固定絕緣片/PWB板 A0007、人工八 鎖PWB板 A0008。
- **REQ-IMP-13** 站別強制對照 `EQUIPMENT_OVERRIDES = {"鎖銅排": "OT00420118"}`（以站別為鍵；1011 版自動3／自動4 站位對調）。
- **REQ-IMP-14** KPOV 庫用到、但設備維度沒有的設備代碼，自動補入 `dim_equipment`，AR 綁定與線別篩選才找得到。
- **REQ-IMP-15** 修護報表 `長期措施` 存入 `fact_repair.long_term_measure`。
- **REQ-IMP-16** 客訴報表 Z–AE 欄存為措施層別（有填內容即視為採用）：Z 管理解、AA 技術解 CCSC 攔截、AB 技術解 KPOV 設計消除、
  AC 技術解 KPOV 攔截、AD 技術解 KPIV 防呆、AE 技術解 KPIV 智能監控。未填設備ID／KPOV 編號者標為未對應。
- **REQ-IMP-17** 新增欄位以 `app/migrations.py` 的 `ADDED_COLUMNS` 在啟動時補上，既有資料庫不需重建。

### 13.2 期間篩選（REQ-WIN-01 ~ 03）

- **REQ-WIN-01** 篩選列在線別／屬性／站別旁提供 `期間` 分段按鈕：天／週／月／年＝近 1／7／30／365 天，**預設月**，選中色 `#0086DB`。
- **REQ-WIN-02** 期間同步到網址 `?window=`（預設月不寫入），切換時各分頁表回到第 1 頁。
- **REQ-WIN-03** 連動範圍：象限圖（期初，§13.4）、客訴／製程柱狀圖（§13.5）、等級異動總覽（§13.6）、站別風險地圖（§13.7）。
  **不**連動：站別 Level 分佈圖、趨勢圖、點檢監控、Level 明細。

### 13.3 首頁版面（整線品控力總覽，取代 §8.1）

```
┌ 側邊導覽 ┬───────────────────────────────────────────────────────────┐
│          │ WJ1 DCS 品控力風險智控平台            ● 線上 N 人  [匯入資料] │
│          ├───────────────────────────────────────────────────────────┤
│          │ 線別▾  屬性▾  站別▾   期間 [天|週|月|年]                       │
│          ├──────────────────────────────┬────────────────────────────┤
│          │ 象限圖（期初 → 現在）           │ 等級異動總覽                 │
│          │ Level 0~3 計數列               │ [高風險 N] [已改善 M]        │
│          │ 客訴柱狀圖（站別 × Level）      │ 措施表（9 欄，§13.6）        │
│          │ 製程柱狀圖（站別 × Level）      │                            │
│          ├──────────────────────────────┴────────────────────────────┤
│          │ 整線 Layout（熱區點選）                                      │
│          │ 站別 Level 分佈（站別 × Level，KPOV 原始 Level）              │
│          │ 站別風險地圖（18 站卡片）                                     │
│          ├──────────────────────────────┬────────────────────────────┤
│          │ 等級異動趨勢圖                  │ Level 3 點檢監控             │
└──────────┴──────────────────────────────┴────────────────────────────┘
```
頁尾顯示資料批次檔名與匯入時間（REQ-UI-14）。

### 13.4 象限圖：期初 → 現在（REQ-QUAD-01 ~ 05）

- **REQ-QUAD-01** 母體固定為**全部 KPOV**（目前 331），四格合計不隨期間變動。
  （取代先前「只計入期間內有維修或客訴的 KPOV」的做法——該做法讓四格合計只有十幾個，易被誤讀。）
- **REQ-QUAD-02** 每格大字顯示 `期初 → 現在`：
  - 期初（灰）＝期間第一天當時的 Level：`build_states(as_of = now − 期間天數)`，只套用生效時間不晚於該時點的事件。
  - 現在（黑）＝套用到今天為止所有已生效事件後的 Level（預計改善不算）。
  - 期間涵蓋全部事件時（例：年），期初等於 KPOV 原始 Level。
- **REQ-QUAD-03** 大字下方顯示增減（`▲+n`／`▼-n`／`持平`，顏色依 REQ-UI-17）與現在的佔比；圖上方一行說明
  「每格數字：期初（近 N 天的第一天）→ 現在（KPOV 數，共 331）」。
- **REQ-QUAD-04** 點格子開 Level 明細：依**現在**的 Level 列出全部 KPOV（不受期間影響），筆數與格子右邊數字一致；保留「僅顯示有異動」開關（REQ-UI-21）。
- **REQ-QUAD-05** 有篩選時仍顯示 `全廠 N`（REQ-UI-04）。

### 13.5 站別 × Level 柱狀圖（REQ-BAR-01 ~ 05）

三張圖共用同一個元件（`StationLevelChart`）：X 軸各站、每站四根柱子 Level 0～3，柱色同四象限並加深色描邊，柱頂標數值（0 不標）。

- **REQ-BAR-01** 站別以**設備代碼**區分（同名站可能是不同設備），順序依 KPOV 庫列序（製程順序）。
  站名用 Layout 顯示名稱（去掉「（人工三）」這類括號補註），先在「/」斷行、每行最多 5 字；站數多時在框內左右捲動。
- **REQ-BAR-02** **站別 Level 分佈**（Layout 下方）：各站 KPOV 個數，依 KPOV 庫**原始 Level**；全線一覽，不套用篩選與期間。
- **REQ-BAR-03** **客訴柱狀圖**：期間內（依客訴日期）各站客訴筆數，Level 取**改善前**；套用線別／屬性／站別篩選。
  未填設備ID 者無法歸站，於圖下方註明筆數。
- **REQ-BAR-04** **製程柱狀圖**：期間內（依測試時間）各站維修筆數，Level 取該筆**惡化事件後**的 Level；套用篩選。
  算不出 Level 者（KPOV 不在 KPOV 庫）於圖下方註明筆數。
- **REQ-BAR-05** 客訴與製程的明細表不在首頁顯示，改由側邊導覽的清單頁查看（§13.10）。

### 13.6 等級異動總覽與措施表（REQ-CHG-01 ~ 06）

- **REQ-CHG-01** 兩張卡片：**高風險**（期間內發生的惡化，依測試時間）、**已改善**（期間內生效的改善，依改善時間；預計改善不算）。點卡片切換下方清單，後端分頁每頁 10 筆。
- **REQ-CHG-02** 措施表九欄（`MeasureTable`，等級異動總覽、客訴清單、製程清單共用）：
  `高風險站別｜高風險KPOV｜Level 等級變化(原)｜緊急措施｜長期措施｜措施層別｜Level 等級變化(變化後)｜改善時間｜客訴筆數`

  | 欄位 | 維修列 | 客訴列 |
  |---|---|---|
  | Level(原) | 惡化事件前→後，下方為發生日 | 改善前單一等級 |
  | 緊急措施 | 改善措施；下方紅字＝`修復時間` | 對策內容；下方紅字＝預計完成時間 |
  | 長期措施 | `long_term_measure` | — |
  | 措施層別 | ⚠ v2.0：改讀 Excel 8D 區塊（REQ-V2-MEAS-01） | Excel Z–AE 欄摘要（唯讀） |
  | Level(變化後) | 改善事件前→後；未到者標「預計」 | 改善前→改善後 |
  | 改善時間 | `改善時間`；未到者標「預計改善」，逾期標「預計・已逾期」 | 實際完成時間（未完成顯示預計） |
  | 客訴筆數 | 0 | 實際筆數 |

  表頭底色 `#1F5C7A`、最小寬度 60rem，窄欄位內左右捲動；點有對應 KPOV 的列開歷程時間軸。
- ⚠ v2.0 已移除（手動分類改由 Excel 提供，見 REQ-V2-MEAS-02）：**REQ-CHG-03** 緊急措施分類（`PUT /emergency-measures`，upsert）：技術解／管理解二選一；技術解再選 KPOV（設計消除、設備攔截）或 KPIV（防呆、智能監控），可複選；管理解填說明文字。切換分類時另一組勾選一律清除。
- ⚠ v2.0 已移除（手動分類改由 Excel 提供，見 REQ-V2-MEAS-02）：**REQ-CHG-04** 只有「高風險」清單可編輯分類（在該列下方展開編輯器）；已改善與製程清單唯讀，同一筆維修共用同一份分類。
- ⚠ v2.0 已移除（手動分類改由 Excel 提供，見 REQ-V2-MEAS-02）：**REQ-CHG-05** 分類以（維修序號, KPOV 編號, 設備代碼）為自然鍵存於 `emergency_measure`，**不掛匯入批次**，重新匯入不會遺失。
- ⚠ v2.0 已移除（手動分類改由 Excel 提供，見 REQ-V2-MEAS-02）：**REQ-CHG-06** 摘要文字格式：`技術解・KPOV：設計消除、設備攔截`／`管理解：說明`／`未分類`。

### 13.7 站別風險地圖（REQ-RISK-01 ~ 04）

- **REQ-RISK-01** 18 站卡片（Layout 熱區 12 站＋未放上熱區的 OP 人工站），標示 CTP／OP、站名、期間內維修與客訴筆數。
- **REQ-RISK-02** 卡片底色＝期間內維修／客訴「發生當時」最嚴重的 Level 顏色（維修取惡化後 Level、客訴取改善前 Level）；
  期間內無事件為 Level 0 綠色；有事件但算不出 Level 為白底並標「Level 未知」；Level 3 標「高風險・L3」。不顯示圖例。
- **REQ-RISK-03** 點卡片等同點 Layout 熱區（下方趨勢與點檢監控切到該站），再點取消。
- **REQ-RISK-04** 不套用上方篩選（全線一覽）；未填設備ID 的客訴另列「另有 N 筆客訴未對應站別」連到客訴清單。

### 13.8 歷程時間軸與 PCN／ECN（REQ-UI-19 補充）

- 時間軸由新到舊：預計改善 → 現況 → 維修事件與 PCN／ECN 依日期交錯 → 基準。同一天時 PCN／ECN 排在維修事件之後（較舊）。
- PCN 以（KPOV 編號, 設備ID）對應，無設備ID 時以（KPOV 編號, 站別）；ECN 影響站別與設備ID 皆為 NA 時視為全廠。
- PCN／ECN 只標示時間與前後狀態，**不參與等級計算**。

### 13.9 Level 3 點檢監控與拍照點檢（REQ-CHK-01 ~ 05）

- **REQ-CHK-01** 點檢項目來自 `高風險項點檢` 工作表，每次匯入重建；點檢紀錄（AR 逐項點檢、拍照點檢）持續累積，
  以（設備代碼, KPOV 編號, 點檢內容）自然鍵對應，不建外鍵。
- **REQ-CHK-02** 班別：日班 08:00–18:00、夜班 20:00–06:00（廠區時區 UTC+8，`QCM_SITE_UTC_OFFSET` 可調）。兩班之間的空檔顯示剛結束的那一班。
- **REQ-CHK-03** 每個項目依點檢間隔把班別切成時段（例：10 小時班、每 2 小時一次＝5 格，20%→100%；⚠ v2.0「開線/班」＝每班 1 格，見 REQ-V2-CHK-02）；
  每格取該時段內最後一次點檢：正常（綠）、異常（紅，仍算完成）、已過未點（漏檢）、進行中、未到。同一時段點多次只算一格。
- **REQ-CHK-04** 項目狀態：正常、異常、逾期（最近一次正常但已超過間隔）、從未點檢。監控表每分鐘重抓。
- **REQ-CHK-05** 拍照點檢（`/ar/photo`）：免掃碼，選站別→項目→拍照上傳，**照片上傳成功即記一次點檢**，預設正常、可回報異常。
- **REQ-CHK-06** 點檢儀表板（`/ar/dashboard`）**只顯示拍照點檢**（AR 掃碼紀錄不顯示，資料保留）：
  - 站別良率卡片：依設備代碼彙總正常／異常次數與良率。
  - 篩選：站別、開始／結束時間。
  - 紀錄表欄位：`站別（KPOV・點檢內容、KPIV 管控等級、備註）｜狀態｜點檢時間｜照片`（⚠ v2.0 拿掉「操作」欄，見 REQ-V2-CHK-04）。
  - 照片欄為 48px 縮圖，點擊後在頁面上彈出大圖（站別、項目、狀態、時間、在新分頁開啟原圖），可按 ✕、點背景或 Esc 關閉；
    照片檔遺失時顯示「照片遺失」。
  - ⚠ v2.0 已移除：點檢紀錄不可刪除（REQ-V2-CHK-04）。
  - 「匯出紀錄（含照片）」依目前的站別與時間篩選匯出，格式見 REQ-CHK-08。
- **REQ-CHK-07** 時間的儲存與顯示：資料庫與 API 一律用 **UTC，且輸出必須帶時區**（`+00:00`；SQLite 讀回不帶時區，須經 `check_monitor.utc()` 補上）。
  前端以 `new Date()` 轉成本地時間顯示（`utils/datetime.ts` 的 `formatLocalDateTime`），**不得直接截字串**；
  `datetime-local` 輸入框的值須先轉成帶時區的 ISO 再送後端。匯出的 Excel 換成廠區時間並在表頭註明時區。
  > 修正前儀表板直接截 `isoformat()` 字串，顯示的是 UTC，比首頁點檢監控慢 8 小時。
- **REQ-CHK-08** 點檢紀錄匯出（`GET /check-inspections/export`，Excel）：
  - 篩選條件與列表相同（站別、開始／結束時間），依點檢時間**由舊到新**排列。
  - 欄位：`日期｜班別｜點檢時間（UTC+8）｜站別｜設備代碼｜KPOV 編號｜點檢內容｜點檢結果｜備註｜照片｜原圖連結`。
  - 班別（`check_monitor.shift_of`）：白班 08:00–18:00、夜班 20:00–06:00（廠區時間）；
    空檔 18–20 歸白班、06–08 歸夜班（剛結束的班，與首頁一致）；夜班跨午夜時「日期」記為開班日。
    匯出用「白班」，首頁沿用「日班」（`EXPORT_SHIFT_NAMES`）。
  - 照片：以 Pillow 縮成寬 240px 的 JPEG（依 EXIF 轉正）嵌入「照片」欄；照片檔不存在或無法讀取時寫「照片遺失」。
  - 原圖連結：前端帶 `baseUrl`（`window.location.origin`）組成可點的超連結；`baseUrl` 只接受 http／https。
  - 點檢結果為異常時以紅色粗體標示；表頭凍結。
  - 最多 1000 筆（取最新的 1000 筆）；超過時在表頭上方加提醒列，並回應標頭 `X-Export-Truncated: 1`。沒有符合的紀錄回 404。
  - 檔名 `點檢紀錄_<廠區時間>.xlsx`（`filename*` 以 RFC 5987 編碼）。

### 13.10 客訴回饋清單、製程異常清單

- `/complaints`：客訴報表（8D），後端分頁、關鍵字搜尋，新到舊。⚠ v2.3：關鍵字搜尋移除，改為 §17 的篩選。
- `/process`：修護報表，每筆維修一列，依測試時間新到舊。
- 兩頁皆使用 §13.6 的措施表欄位；客訴未對應 KPOV 者標「未對應 KPOV」。

### 13.11 外殼與導覽（REQ-NAV-01 ~ 05）

- **REQ-NAV-01** ⚠ v2.0 平台名稱改為 **CNE WJ1 DCS 品控力風險智控平台**（REQ-V2-NAV-01）；側邊欄標題與頁首一致，標題**一行顯示不換行**（側邊欄寬 17rem）。
- **REQ-NAV-02** ⚠ v2.0 已由 REQ-V2-NAV-02 取代。原側邊導覽分組：
  - 品質管控：整線品控力總覽、客訴回饋清單、製程異常清單
  - AR 點檢：點檢儀表板、拍照點檢
  - 選中項目為反藍 `#0086DB`、白字。
- **REQ-NAV-03** 桌機側邊欄可**固定**或**收合**：固定時常駐展開並推開內容；收合成 48px 窄條，滑過或點 ☰ 時浮出、移開或換頁收回；選擇記在瀏覽器（`localStorage`，失敗時預設固定）。手機版為抽屜。
- **REQ-NAV-04** AR 設備管理與 AR 掃描點檢以 `frontend/src/features.ts` 的 `AR_MARKER_ENABLED = false` 暫時關閉（路由、導覽、儀表板連結一併隱藏），程式保留。
- **REQ-NAV-05** 頁首顯示線上人數（以 heartbeat 統計開著本站的分頁數）。

### 13.12 API 一覽（v1.4 新增與修訂）

| 端點 | 說明 |
|---|---|
| `GET /quadrant?view=&station=&line=&attribute=&target=&window=` | 母體全部 KPOV；給 `window` 時回 `start`（期初分佈），否則 `start: null` |
| `GET /kpov?...&window=` | `window` 保留相容，不再篩選 |
| `GET /trend` | 等級異動趨勢（累計惡化／累計改善） |
| `GET /level-changes?window=&kind=escalated或improved&page=` | 等級異動總覽，`counts` 兩張卡片＋措施表列 |
| `PUT /emergency-measures` | 緊急措施分類 upsert（§13.6） |
| `GET /station-risk?window=` | 各設備維修／客訴筆數與 `worstLevel`、`unmappedComplaints` |
| `GET /station-levels/kpov` | 各站 KPOV 原始 Level 分佈（站別依製程順序） |
| `GET /station-levels/events?window=&station=&line=&attribute=` | 各站期間內客訴／維修筆數（依 Level），另回 `unmappedComplaints`、`unknownLevel` |
| `GET /complaints/summary`、`GET /process/summary` | 客訴／製程追蹤（首頁已不使用，保留） |
| `GET /complaints`、`GET /repairs` | 客訴、製程清單頁（分頁、關鍵字）⚠ v2.3：改為 §17 的篩選與完成期限 |
| `GET /check-monitor`、`GET /check-items`、`POST /check-inspections` | Level 3 點檢監控、拍照點檢 |
| `GET /check-inspections?equipmentCode=&start=&end=&limit=` | 點檢儀表板：拍照點檢紀錄（新到舊，`inspectedAt` 帶時區的 UTC） |
| `GET /check-inspections/stats` | 依設備（站別）彙總的正常／異常次數與良率 |
| `DELETE /check-inspections/{id}` | 刪除拍照點檢紀錄與照片檔 |
| `GET /check-inspections/export?equipmentCode=&start=&end=&baseUrl=` | 匯出 Excel：班別、點檢結果、照片縮圖（REQ-CHK-08） |
| `POST /presence/heartbeat`、`POST /presence/leave` | 線上人數 |
| `GET /kpov/{kpovNo}/{equipmentCode}/history` | 新增 `changes`（PCN／ECN） |

`window` 一律為 `day|week|month|year`，其他值回 422。


---

## 14. v2.0 功能規格（qcm-system-v3，2026-10-20）

### 14.1 資料來源：數據庫-1019（REQ-V2-IMP-01 ~ 08）

- **REQ-V2-IMP-01** 只支援 `數據庫-1019.xlsx` 格式；測試只以 1019 驗證（不再用 1008／1011／raw_data）。
- **REQ-V2-IMP-02** 修護報表表頭在第 5 列（上方 4 列為 8D 分組標題）；表頭掃描列數為 8。基本欄位（A–S、BJ–BT）以名稱對應。
- **REQ-V2-IMP-03** 修護報表新增 **BM 緊急措施、BN 緊急措施時間**，存 `fact_repair.emergency_measure(_at)`。
- **REQ-V2-IMP-04** **8D 區塊**：客訴報表 I–AX 與修護報表 T–BI 結構完全相同（修護整段右移 11 欄）。欄位定義只有一份
  （`mapping.EIGHT_D_COLUMNS`，以客訴欄位字母為準），以 `EIGHT_D_HEADER_CHECKS` 的表頭文字驗證位置；
  全部對上才讀，部分對上則警告並略過（不讀錯欄）。修護報表的 8D 欄位在 `fact_repair` 加 `d8_` 前綴。
  欄位：現狀（製程單元、Y 檢測項目／偵測方式／偵測度、y 產品 KPOV／偵測方式／偵測度、品質管控力、KPIV 因子／防呆防錯有無與方式／
  監控方式與說明／x 管控等級）、原因（發生、流出）、對策（管理解判定、管理對策、技術解五項、對策內容、責任人、預計／實際完成時間、有效性判定）、
  改善後（同現狀）、改善判定。
- **REQ-V2-IMP-05** 偵測方式字典（BW–BX）：挑選相鄰兩欄時**先比「不同分數的個數」再比筆數**——8D 區塊的「偵測方式／偵測度」欄
  分數大量重複，字典則 1–10 分各一種，避免誤抓（1019 版正確為 9 筆）。
- **REQ-V2-IMP-06** 客訴報表 BA 緊急措施、BB 緊急措施時間、改善時間、改善措施以**表頭文字**定位（位置可能再變）。1019 版只有 1 筆客訴（使用者確認）。
- **REQ-V2-IMP-07** 高風險項點檢：點檢內容欄接受「KPIV(x) 點檢內容」（舊名「點檢內容」亦可）；新增 **KPIV(x) 管控等級**
  （例「A: 防呆防錯+智能」「B／E: 防呆防錯+人工」）存 `fact_check_item.kpiv_control_level`。1019 版 10 項。
- **REQ-V2-IMP-08** 新欄位登錄於 `migrations.ADDED_COLUMNS`，既有資料庫啟動時自動補欄。

### 14.2 等級事件（REQ-V2-LIFE-01）

- **REQ-V2-LIFE-01** IMPROVE 生效時間**不得早於同一筆維修的測試時間**：改善時間多半只填日期（00:00），若早於當天稍晚的不良，
  以測試時間為準。否則事件會先套改善再套不良，現況停在惡化後的等級，前後等級也接不起來（例：K00051@A0006，修正後現況 L0）。

### 14.3 措施表與 8D 明細（REQ-V2-MEAS-01 ~ 04）

- **REQ-V2-MEAS-01** 措施表欄位來源（維修與客訴一致）：
  | 欄位 | 來源 |
  |---|---|
  | 緊急措施（下方紅字時間） | 緊急措施／緊急措施時間（修護 BM／BN；客訴同名欄） |
  | 長期措施（下方時間） | 改善措施／改善時間（修護 BR／BQ；客訴同名欄） |
  | 措施層別 | 8D 區塊的管理對策與技術解五項（有填即採用），摘要如「管理解／技術解・KPOV：設備攔截；KPIV：防呆防錯」，**唯讀** |
  | 改善時間 | 維修：IMPROVE 生效時間；客訴：改善時間，沒有時以實際完成時間（未完成以預計代替並標示） |
- **REQ-V2-MEAS-02** 移除系統內手動「措施層別」分類：`PUT /emergency-measures` 與前端編輯器刪除；`emergency_measure` 表保留但不再讀寫。
- **REQ-V2-MEAS-03** 措施表、製程風險管理、客訴案件管理的列可點，開啟**明細側欄**（`RecordDetailDrawer`）：
  - 「8D 明細」分頁：基本資料、緊急措施、長期措施（改善措施）、8D 四段（現狀盤查 → 原因 → 改善對策 → 改善後盤查）。
  - 「等級歷程」分頁：該 KPOV×設備 的時間軸（REQ-UI-19）。按 ✕ 或 Esc 關閉。
- **REQ-V2-MEAS-04** API：`GET /repairs/{id}`、`GET /complaints/{id}`（含 `eightD`）；`/repairs`、`/complaints` 清單列加 `emergencyMeasure(At)`、`improvement(At)`；
  措施表列加 `repairId`／`complaintId`，`longTerm` 改為 `{text, at}`，`layer` 只剩 `summary`。

### 14.4 點檢（REQ-V2-CHK-01 ~ 04）

- **REQ-V2-CHK-01** 點檢項目顯示 **KPIV(x) 管控等級**標籤（A 綠、B 藍、C 黃、D 橘、E 紅），出現在首頁點檢監控、拍照點檢、點檢看板。
- **REQ-V2-CHK-02** 點檢頻率只有「開線/班」時＝**每班一次**（間隔＝班長 10 小時，進度 1 格）；有「巡檢: 2h/次」時維持 2 小時一格。
- **REQ-V2-CHK-03** 點檢內容改版後，**舊項目底下的點檢紀錄不顯示**：點檢看板、統計、匯出只列目前生效批次點檢項目（設備＋KPOV＋點檢內容）的紀錄；首頁監控本來就只看目前項目。
- **REQ-V2-CHK-04** **點檢紀錄不可刪除**（稽核證據）：點檢看板拿掉「操作／刪除」欄，後端移除 `DELETE /check-inspections/{id}`。

### 14.5 時間顯示（REQ-V2-TIME-01）

- **REQ-V2-TIME-01** 實際時刻（測試時間、點檢時間、匯入時間）一律以 `formatLocalDateTime` 轉本地時間顯示，不得截 ISO 字串；
  只有日期意義的欄位（緊急措施時間、改善時間、預計／實際完成）以日期顯示。修正前製程頁與措施表的發生日會差 8 小時。

### 14.6 外殼與導覽（REQ-V2-NAV-01 ~ 03）

- **REQ-V2-NAV-01** 平台名稱 **CNE WJ1 DCS 品控力風險智控平台**（側邊欄標題、瀏覽器分頁標題），標題一行不換行。
- **REQ-V2-NAV-02** 側邊導覽（平台_左邊目錄列修改方案 1015）：拿掉「品質管控」分組列；第一層
  **總覽 Overview**（`/quality`）、**製程風險管理 Process Risk Mgmt**（`/process`，修護報表）、**客訴案件管理 RMA Event**（`/complaints`）；
  **點檢控制中心 Inspection Control Center** 為兩層：**點檢看板 Dashboard**（`/ar/dashboard`）、**拍照點檢 Photo Verification**（`/ar/photo`）。
  各頁頁首標題與導覽名稱一致。
- **REQ-V2-NAV-03** 總覽頁**暫時拿掉 PM1 整線 Layout 圖**（`LayoutMap` 元件保留）；站別 Level 分佈與站別風險地圖照常顯示，點卡片仍可切換下方範圍。

### 14.7 部署：Cloudflare（REQ-V2-DEP-01 ~ 06）

- **REQ-V2-DEP-01** 架構：Cloudflare Worker（`cloudflare/src/index.ts`）提供前端靜態檔（`frontend/dist`，SPA），
  `/api/*`、`/health` 轉給後端容器（`@cloudflare/containers`，`backend/Dockerfile`）。步驟見 `DEPLOY.cloudflare.md`。
- **REQ-V2-DEP-02** 資料庫：容器內 SQLite（`/app/data/qcm.db`，WAL 模式、busy_timeout 5 秒），由 **Litestream v0.5.17**
  持續備份到 R2 的 `db/`（約每秒同步）；容器啟動時先 `litestream restore -if-replica-exists -if-db-not-exists` 再
  `litestream replicate -exec` 執行後端（`QCM_LITESTREAM=1` 啟用，見 `backend/docker-entrypoint.sh`）。不使用 D1（無交易、需重寫資料層）。
- **REQ-V2-DEP-03** 上傳檔（照片、AR 設備圖）經儲存層 `services/storage.py`：`QCM_STORAGE=local`（預設，磁碟）或 `s3`（R2，S3 相容 API，
  `QCM_S3_ENDPOINT／BUCKET／ACCESS_KEY_ID／SECRET_ACCESS_KEY／REGION`）。對外網址一律 `/api/ar/uploads/<key>`，由後端讀出回傳；
  key 只允許「子目錄/檔名.副檔名」，禁止 `..`。
- **REQ-V2-DEP-04** 後端只能 1 個執行個體（`max_instances: 1`；SQLite 單一寫入者＋線上人數在記憶體），`getContainer` 固定同一名稱。
  閒置 30 分鐘休眠（`sleepAfter`），喚醒時自 R2 還原。
- **REQ-V2-DEP-05** R2 金鑰以 `wrangler secret put` 設定，不進版控；`cloudflare/.dev.vars` 列入 `.gitignore`。
- **REQ-V2-DEP-06** 本機驗證：`cloudflare/docker-compose.sim.yml`（後端不掛 volume、SeaweedFS 扮演 R2、nginx 扮演 Worker 路由），
  刪除重建後端容器後資料與照片須完整還原（Windows 的 `wrangler dev` 不支援容器）。

### 14.8 驗收條件（v2.0，以數據庫-1019 為準）

| # | 條件 |
|---|---|
| **AC-V2-1** | 匯入：偵測方式字典 9 筆、KPOV 331、維修 28、等級事件 52、點檢項目 10、客訴 1；無查不到字典的偵測方式 |
| **AC-V2-2** | 28 筆維修皆有緊急措施與時間；8D 欄位（例 ALG25B01310WB：Level 2 → 0、責任人肖華陽、預計 2025-12-30、實際 2026-04-08） |
| **AC-V2-3** | 客訴序號 1：緊急措施「1. 已導入使用智能電鎖…」2026-05-11、改善措施 2025-12-05、KPIV 管控等級 E → A |
| **AC-V2-4** | 點檢監控：「開線/班」項目 1 格、K00053 巡檢 2h 為 5 格；鎖軟銅排2 為 OT00420108、管控等級 A |
| **AC-V2-5** | K00051@A0006（IOW26A00347W0）：改善不早於不良，現況 Level 0 |
| **AC-V2-6** | `PUT /emergency-measures`、`DELETE /check-inspections/{id}` 皆不存在（404／405） |
| **AC-V2-7** | e2e：瀏覽器開前後端，逐頁檢查並截圖存於 `docs/e2e/` |
| **AC-V2-8** | Cloudflare 模擬：S3 模式下照片寫入 bucket 並可經 `/api/ar/uploads` 讀取；後端容器刪除重建後，資料庫（331 KPOV）與照片自 R2 還原；還原後的新寫入在下次重建後仍在 |
| **AC-V2-9** | `wrangler deploy --dry-run` 通過（設定、容器映像建置、靜態檔） |

---

## 15. v2.1 權限控管 RBAC（2026-10-26）

### 15.1 角色與權限（REQ-RBAC-01 ~ 06）

| 角色 | 代碼 | 看資料 | 拍照點檢 | 匯入 Excel | 使用者管理 |
|---|---|---|---|---|---|
| 最高權限管理者 | `super_admin` | 所有廠 | ✓ | 任何廠 | 所有帳號；**唯一能指派廠管理者** |
| 廠管理者 | `plant_admin` | 自己的廠 | ✓ | 只限檔名廠別＝自己的廠 | 自己廠的一般使用者（新增、改名、停用／啟用、重設密碼） |
| 一般使用者 | `user` | 自己的廠 | ✓ | ✗ | ✗ |

- **REQ-RBAC-01** 權限只管到**廠**（WJ1～WJ8）；同一個廠的所有線都看得到。
- **REQ-RBAC-02** 「修改內容」＝匯入新的 Excel；只有管理者能匯入。一般使用者畫面上不顯示「匯入資料」與「系統管理」。
- **REQ-RBAC-03** 廠管理者新增帳號時，角色固定為一般使用者、廠別固定為自己的廠（後端強制，不採用前端送來的值）。
- **REQ-RBAC-04** 角色與廠別只有最高權限管理者能改；任何人都不能停用自己、也不能改自己的角色或廠別。
- **REQ-RBAC-05** 拍照點檢的照片 `/api/ar/uploads/checks/…` 需登入，且照片所屬資料集的廠必須是使用者可看的廠；
  其他上傳檔（AR 設備圖檔）只開放最高權限管理者。照片回應 `Cache-Control: private, no-store`，登出後不能從瀏覽器快取看到。
- **REQ-RBAC-06** AR 掃碼相關 API（`/api/ar/*`，功能已關閉）只開放最高權限管理者。

### 15.2 帳號與登入（REQ-AUTH-01 ~ 07）

- **REQ-AUTH-01** 帳號由系統自建（資料表 `app_user`）：帳號（唯一，英數字與 `_ . - @`，3～64 字）、名稱、角色、廠別（最高權限管理者為空）、
  啟用狀態、`token_version`、建立時間、最後登入時間。
- **REQ-AUTH-02** 密碼至少 8 碼；以 scrypt＋隨機 salt 雜湊儲存，比對用常數時間。
- **REQ-AUTH-03** 登入成功發 JWT（HS256，有效 12 小時），放在 httpOnly cookie `qcm_session`（SameSite=Lax；HTTPS 時加 Secure，依 `X-Forwarded-Proto` 判斷）。
  前端碰不到權杖。簽章金鑰為 `QCM_JWT_SECRET`；未設定時以隨機值啟動並警告（重啟後所有人需重新登入）。
- **REQ-AUTH-04** 每次請求都回資料庫確認帳號仍啟用、且權杖的 `ver` 等於 `token_version`。停用、重設密碼、修改密碼、變更角色或廠別時
  `token_version` 加一，該帳號的舊權杖立即失效。
- **REQ-AUTH-05** 除 `/health` 與 `POST /api/v1/auth/login` 外，所有 `/api/*` 都需登入（未登入 401）。前端收到 401 一律回登入頁，
  登入後回到原本的頁面。
- **REQ-AUTH-06** 啟動時若資料庫沒有任何最高權限管理者，依 `QCM_ADMIN_USERNAME`／`QCM_ADMIN_PASSWORD` 建立第一位（名稱「系統管理員」）；
  未設定或密碼不符規則時只記錄警告、不建立。已有最高權限管理者後，這兩個變數不再有作用。
- **REQ-AUTH-07** 停用的帳號登入回 403「帳號已停用，請洽管理者」；帳號或密碼錯誤回 401「帳號或密碼錯誤」（不區分帳號是否存在）。

### 15.3 資料集：一條線的生效資料（REQ-DS-01 ~ 06）

- **REQ-DS-01** 匯入檔名規則：`^(WJ[1-8])-([A-Za-z0-9]+)-([A-Za-z0-9]+)-數據庫-(\d{4})\.xlsx?$`，即
  `廠-產品廠-線別-數據庫-月日.xlsx`（例 `WJ1-DCS-PM1-數據庫-1026.xlsx`）。不符合回 422，訊息附正確範例。
- **REQ-DS-02** 資料集 key＝`廠-產品廠-線別`（例 `WJ1-DCS-PM1`）。`import_batch` 新增 `plant`、`factory`、`line_code`、`dataset`、`data_date`。
- **REQ-DS-03** 每個資料集只有一個生效批次：匯入時只停用**同一資料集**的舊批次；沿用上一批與維修累積也只看同一資料集。
- **REQ-DS-04** 拍照點檢紀錄 `check_photo_inspection.dataset` 記錄所屬的線（不同廠可能有相同設備代碼）；列表、統計、匯出依目前資料集過濾。
- **REQ-DS-05** 前端以 header `X-QCM-Dataset` 指定資料集；瀏覽器直接下載（匯出 Excel）改用 `?dataset=`，權限檢查相同。
  未指定時用使用者可看的第一個資料集。指定別廠回 403；該資料集尚無資料回 404「尚無資料，請管理者匯入 Excel」。
- **REQ-DS-06** 舊版資料升級時（`migrations.ensure_schema` 補欄位）一律歸到 `WJ1-DCS-PM1`。

### 15.4 API

| 方法 | 路徑 | 權限 | 說明 |
|---|---|---|---|
| POST | `/api/v1/auth/login` | 公開 | `{username, password}`；設 cookie，回使用者 |
| POST | `/api/v1/auth/logout` | 登入 | 清除 cookie |
| GET | `/api/v1/auth/me` | 登入 | 使用者＋可看的 `datasets` |
| POST | `/api/v1/auth/password` | 登入 | `{oldPassword, newPassword}` 改自己的密碼 |
| GET | `/api/v1/datasets` | 登入 | 可看的生效資料集：`key, plant, factory, line, filename, importedAt` |
| GET／POST | `/api/v1/users` | 管理者 | 列表（廠管理者只看自己廠）／新增 |
| PATCH | `/api/v1/users/{id}` | 管理者 | `{displayName?, role?, plant?, isActive?}`；角色與廠別限最高權限管理者 |
| POST | `/api/v1/users/{id}/reset-password` | 管理者 | `{password}` |
| POST | `/api/v1/import` | 管理者 | 依檔名決定資料集；回傳 `batch.dataset` |

其餘 `/api/v1/*` 不變，皆依 §15.3 的資料集取資料。

### 15.5 畫面（REQ-RBAC-UI-01 ~ 05）

- **REQ-RBAC-UI-01** 登入頁 `/login`：帳號、密碼、錯誤訊息；「忘記密碼請洽各廠管理者重設」。
- **REQ-RBAC-UI-02** 頁首：**廠／線別**下拉（依廠分組；只有一個資料集時顯示文字；沒有資料時顯示「尚無資料」），
  切換後各頁重新載入；選擇記在瀏覽器（`localStorage qcm.dataset`），失效時改用第一個。
- **REQ-RBAC-UI-03** 頁首右側使用者選單：名稱、角色・廠別、帳號、**修改密碼**、**登出**。
- **REQ-RBAC-UI-04** 匯入對話框標明檔名格式；匯入成功後更新線別清單並切到剛匯入的線。總覽「尚無資料」畫面包在頁框內（仍可登出、切換線別）；
  一般使用者看到「請洽廠管理者匯入 Excel」。
- **REQ-RBAC-UI-05** 側邊欄「系統管理 › 使用者管理」（`/admin/users`，只有管理者看得到，一般使用者直接開會被導回總覽）：
  表格（帳號、名稱、角色、廠別、狀態、最後登入）、新增、編輯、重設密碼、停用／啟用。廠管理者的角色與廠別欄位鎖定。

### 15.6 部署設定（REQ-RBAC-DEP-01）

| 變數 | 說明 |
|---|---|
| `QCM_JWT_SECRET` | 必填（長隨機字串）；改掉會讓所有人登出 |
| `QCM_ADMIN_USERNAME`／`QCM_ADMIN_PASSWORD` | 第一位最高權限管理者（只在還沒有時建立） |

VM：`docker-compose.yml`／`.env.example`／`DEPLOY.vm.md`；Zeabur：`DEPLOY.zeabur.md` 的 api Variables；
Cloudflare：`wrangler secret put`（`cloudflare/src/index.ts` 有設定才傳入）。

### 15.7 驗收條件

| # | 條件 |
|---|---|
| **AC-RBAC-1** | 未登入呼叫 `/api/v1/*`、照片網址皆 401；帳密錯誤 401；JWT 竄改或過期無效 |
| **AC-RBAC-2** | 三個資料集（WJ1-DCS-PM1、WJ1-DCS-PM2、WJ2-DCS-PM1）各自生效；重新匯入 PM1 不影響 PM2 |
| **AC-RBAC-3** | WJ2 一般使用者只看得到 WJ2 的線；指定 WJ1（header 或 `?dataset=`）403；匯入 403；使用者管理 403 |
| **AC-RBAC-4** | WJ2 廠管理者：匯入 WJ1 檔名 403、WJ2 檔名成功；不能建立廠管理者；看不到也改不了別廠帳號；不能停用自己 |
| **AC-RBAC-5** | 不合格檔名 422 且訊息含範例；密碼少於 8 碼 422；帳號重複 409 |
| **AC-RBAC-6** | 停用帳號或重設密碼後，舊權杖立即 401；停用帳號再登入 403 |
| **AC-RBAC-7** | 照片跨廠存取被拒；同廠可看 |
| **AC-RBAC-8** | e2e（截圖 `docs/e2e/2026-10-26-13～26`）：錯誤密碼 → 最高權限管理者匯入三條線、不合格檔名被拒、指派 WJ2 廠管理者 → 廠管理者新增一般使用者（角色／廠別鎖定）、匯入別廠被拒、匯入新線並自動切換 → 一般使用者看不到匯入與系統管理、拍照點檢、看板顯示照片、切線後紀錄隔離 → 帳號被停用後自動回登入頁 |

---

## 16. v2.2 總覽廣播（2026-10-26）

### 16.1 畫面（REQ-BC-01 ~ 05）

- **REQ-BC-01** 總覽頁標題列下方、篩選器上方顯示「廣播」列，三則訊息並排（窄螢幕改為上下排）。
  廣播一律看**目前這條線的全部 KPOV**，**不受線別／屬性／站別篩選器影響**，只跟**期間**（天／週／月／年）連動。
- **REQ-BC-02** a. **Level 3 個數**：期初（期間第一天當時）→ 現在，與象限圖同一套算法（`build_states(as_of=期初)`）。
  - 增加：紅色「增加 N 項（期初 → 現在）」
  - 減少：綠色「減少 N 項（期初 → 現在）」
  - 不變：灰色「無變化，維持 N 項」
- **REQ-BC-03** b. **當班點檢次數**：只看當班（白班 08:00–18:00、夜班 20:00–06:00；兩班之間的空檔顯示剛結束的那一班並標「已結束」），
  「已點檢 X / Y 次」。Y＝所有點檢項目在當班的應點檢時段數，X＝其中已拍照點檢的時段數（與點檢監控的時段相同，§14.4）；
  有異常時加「異常 N」。顏色：有異常紅、全部完成綠、班已結束仍未完成黃、進行中藍。
- **REQ-BC-04** c. **站別等級提升**：期間內有 ESCALATED 事件（依不良發生時間，與等級異動總覽的惡化筆數相同）的站別。
  - 沒有：綠色「無站別等級提升」
  - 有：紅色「N 站提升：」，列出最多 3 站，各站顯示最近一次的 Level 變化（L2 ↑ L3）。超過 3 站時結尾加「等」，滑鼠移上去看完整清單。
- **REQ-BC-05** 每 60 秒自動更新（拍照點檢在其他裝置上進行）；切換期間、匯入新資料、切換線別時立即更新。

### 16.2 API

`GET /api/v1/broadcast?window=day|week|month|year`（登入；資料集依 §15.3）

```json
{
  "window": "month", "since": "…",
  "level3": { "start": 8, "now": 6, "delta": -2 },
  "inspection": {
    "shift": { "name": "夜班", "label": "夜班 20:00–06:00", "start": "…", "end": "…", "ended": false },
    "items": 8, "expected": 24, "completed": 2, "warn": 0
  },
  "escalations": [{ "station": "軟銅排1", "kpovNo": "K00051", "kpovName": "…", "equipmentCode": "…",
                    "levelBefore": 2, "levelAfter": 3, "at": "…" }],
  "escalatedStations": ["軟銅排1"]
}
```

### 16.3 驗收條件

| # | 條件 |
|---|---|
| **AC-BC-1** | 各期間的 `level3` 等於 `/quadrant?window=` 的 `start.level3 → scope.level3` |
| **AC-BC-2** | `inspection.expected／completed` 等於 `/check-monitor` 各項 `slots` 數與 `completed` 加總；班別名稱為白班／夜班 |
| **AC-BC-3** | `escalations` 筆數等於 `/level-changes?window=` 的 `counts.escalated`，且全部為升級 |
| **AC-BC-4** | 未登入 401 |
| **AC-BC-5** | e2e（`docs/e2e/2026-10-26-27～28`）：夜班拍照 2 次後廣播顯示「已點檢 2 / 24 次」；月：Level 3 減少 2 項（8 → 6）、1 站提升（軟銅排1 L2↑L3）；切到年：Level 3 無變化、6 站提升 |

---

## 17. v2.3 完成期限與清單篩選（2026-10-26）

適用：**製程風險管理**（修護報表 `GET /api/v1/repairs`）與**客訴案件管理**（客訴報表 `GET /api/v1/complaints`）。原本的關鍵字搜尋（`q`）移除。

### 17.1 完成期限（REQ-DUE-01 ~ 04）

- **REQ-DUE-01** 一律以 **8D 預計完成時間 vs 實際完成時間** 判定（修護報表 8D 區塊；客訴報表 AH／AI 欄），日期換成廠區當地日期，天數為日曆天：

| 狀態 | 條件 | 逾期天數 |
|---|---|---|
| 預計完成（未到期） | 沒有實際完成，且預計完成 ≥ 今天 | — |
| 逾期 | 有實際完成且實際 > 預計 | 實際 − 預計 |
| 逾期 | 沒有實際完成，且預計完成 < 今天 | 今天 − 預計 |
| 準時完成 | 有實際完成且實際 ≤ 預計 | — |
| 不列入 | 沒有預計完成 | — |

- **REQ-DUE-02** 逾期分組：**7 天內**（1–6 天）、**7–14 天**、**14 天以上**（15 天起）。
- **REQ-DUE-03** 圓餅圖放在頁面最上方，共四塊：預計完成（未到期）＋三組逾期；**準時完成與沒有預計完成的不列入**。中央顯示逾期總數，旁邊列出預計完成數、逾期數與四組圖例。
  圓餅依目前的其他篩選條件統計（不受「完成期限」篩選影響）；點圓餅、圖例或「預計完成／逾期」按鈕即以該組篩選清單，再點一次取消。
- **REQ-DUE-04** 逾期以紅色標示（準時完成以綠色「已完成」＋實際完成日標示；未到期不另加標記）：製程頁在「改善時間」欄（保留原本的「預計改善」標記）下方加紅底「逾期 N 天」與「預計 … ・實際 …（或未完成）」；
  客訴頁的「預計完成」日期轉紅，「實際完成」欄下方加同樣的紅色標記。

### 17.2 篩選（REQ-FLT-01 ~ 03）

| 篩選 | 製程風險管理 | 客訴案件管理 | 參數 |
|---|---|---|---|
| 發生時間（日期範圍） | 測試時間 | 日期（E 欄） | `occurredFrom`、`occurredTo` |
| 多選 | 機種 | **客戶**（客訴報表沒有機種欄位） | `group`（可重複） |
| 多選 | 站別 | 站別（KPOV 對應的站別；對不到時用製程單元） | `station`（可重複） |
| 多選 | KPOV（顯示名稱，值為 KPOV 編號） | 同左 | `kpov`（可重複） |
| 日期範圍 | 改善時間 | 改善時間（BE 欄） | `improvedFrom`、`improvedTo` |
| 單選 | 完成期限：預計完成／已完成（準時）／全部逾期／7 天內／7–14 天／14 天以上 | 同左 | `due`＝`planned`／`ontime`／`overdue`／`lt7`／`d7_14`／`gt14` |

- **REQ-FLT-01** 日期為廠區當地日期（`YYYY-MM-DD`），起訖皆含；有給範圍時沒有該日期的資料不符合。
- **REQ-FLT-02** 多選以重複的查詢參數傳入（`?station=A&station=B`），同一項內為「或」、不同項之間為「且」；篩選改變時回到第 1 頁。
- **REQ-FLT-03** 選項（`options.groups／stations／kpovs`）取自該資料集全部資料，不隨篩選縮減。客訴頁表格新增「站別」「KPOV」「改善時間」欄。

### 17.3 API 回應

兩個清單在原本的分頁欄位外，每列多 `due`（`{status, overdueDays, bucket, plannedAt, doneAt}` 或 `null`），另回：

```json
{ "dueStats": { "planned": 0, "overdue": 9, "lt7": 6, "d7_14": 0, "gt14": 3 },
  "options": { "groups": ["3915102661", "…"], "stations": ["…"], "kpovs": [{ "value": "K00004", "label": "浮鎖" }] } }
```

### 17.4 驗收條件

| # | 條件 |
|---|---|
| **AC-DUE-1** | 單元：未完成且今天到期＝預計完成；未完成過期 7 天＝7–14 天；預計 2025-12-30／實際 2026-04-08＝逾期 99 天（14 天以上）；實際＝預計為準時、不進圓餅；1／6／7／14／15 天分組正確 |
| **AC-DUE-2** | 1026 修護報表 30 筆：逾期 9（7 天內 6、7–14 天 0、14 天以上 3）、預計完成 0；各 `due` 篩選的筆數等於圓餅該組，且圓餅不變；`due=bad` 422 |
| **AC-DUE-3** | 機種、站別（兩站）、KPOV、測試時間 10 月（3 筆）、改善時間篩選結果與逐筆比對一致；測試時間以廠區日期判定 |
| **AC-DUE-4** | 客訴：站別取 KPOV 對應（鎖銅排）、客戶篩選、日期篩選；1019 唯一一筆客訴準時完成 |
| **AC-DUE-6** | 1026 修護報表：`due=ontime` 21 筆，與逾期 9、預計完成 0 合計 30；製程頁改善時間欄與客訴頁實際完成欄顯示綠色「已完成」（`docs/e2e/2026-10-26-33`） |
| **AC-DUE-5** | e2e（`docs/e2e/2026-10-26-29～32`）：製程頁圓餅 9 逾期；點「逾期 14 天以上」清單剩 3 筆且改善時間欄紅色「逾期 29／99 天」；測試時間 8/1–10/31＋機種 3915102661 → 6 筆、逾期 2；客訴頁圓餅與篩選 |

---

## 18. v2.4 點檢看板：趨勢與異常分布（2026-10-26）

### 18.1 畫面（REQ-CHT-01 ~ 04）

- **REQ-CHT-01** 點檢看板「站別良率總覽」卡片上方新增一列，寬螢幕（≥ lg）左右各半、窄螢幕上下排；右上角期間切換「近 7／14／30 天」（預設 14 天），兩張圖共用。
  一律看目前這條線的全部點檢項目，不受下方點檢紀錄的站別／時間篩選影響；按「重新整理」時一併更新。
- **REQ-CHT-02** 左半：**異常次數與漏點檢數**折線（依日）。
  - 異常次數＝拍照點檢結果為異常的次數；依所屬班別的**開班日**歸日（夜班跨午夜算開班當天；兩班之間的空檔歸剛結束的班，與匯出相同）。
  - 漏點檢數＝各點檢項目在當日各班的點檢時段（與點檢監控 §14.4 相同：開線/班一班一格、巡檢依間隔切格）中，**已結束卻沒有拍照點檢**的格數；進行中與未到的時段不算。
  - 漏點檢**從這條線第一筆拍照點檢所在的班開始算**（系統啟用前的日子不算漏點檢）；尚無拍照點檢時不計。標題旁顯示期間內異常與漏點檢總數。
- **REQ-CHT-03** 右半：**KPIV 點檢內容異常分布**圓餅：每個有異常的點檢項目一塊（依異常次數多到少，最多 6 塊，超過的合併為「其他 N 項」），其餘為「正常」一塊（淡灰）；
  中央顯示異常率＝異常次數／期間內全部點檢次數。圖例列出點檢內容、站別、次數與佔全部點檢的百分比。
- **REQ-CHT-04** 顏色：異常線橘、漏點檢線紫；異常扇形為暖色系、正常為淡灰。

### 18.2 API

`GET /api/v1/check-inspections/trend?days=14`（1–90；登入；資料集依 §15.3）

```json
{ "days": 14, "since": "…", "trackingFrom": "…(第一筆點檢所在班的開班時間)",
  "series": [{ "date": "2026-10-25", "warn": 1, "inspected": 2, "missed": 4, "expected": 6 }],
  "items": [{ "station": "…", "equipmentCode": "…", "kpovNo": "…", "checkContent": "…", "kpivControlLevel": "B", "total": 2, "warn": 1 }],
  "totals": { "total": 241, "ok": 217, "warn": 24, "missed": 75 } }
```

### 18.3 驗收條件

| # | 條件 |
|---|---|
| **AC-CHT-1** | 單元：開線/班（一班一格）與每 5 小時（一班兩格）兩項；第一筆點檢之前的日子漏點檢 0；已結束的班未點的格計入漏點檢；夜班 21:00 的異常歸開班日；進行中的班只算已結束的格 |
| **AC-CHT-2** | 沒有拍照點檢時 series 全 0、trackingFrom 為 null；`days=0` 422 |
| **AC-CHT-3** | e2e（`docs/e2e/2026-10-26-34～36`，以模擬的 6 天點檢資料）：左右兩半版面；折線 10/20 起有值、今天日班未點顯示 24 格漏點檢；圓餅異常率 10.0%（241 次中 24 次異常）、6 個點檢項目＋正常；切換 7／14／30 天重新查詢 |
