# 品控力管理系統 — 開發規格書 v1.3

> 規格驅動開發（SDD）：本文件是唯一事實來源。程式碼必須符合本文件；若實作時發現本文件有誤，先改本文件再改程式碼。
>
> 文件狀態：**已鎖定，可開工**（D-01~D-04 已決議，見 §11）
> 最後更新：2026-09-21
>
> v1.1 變更：新增 §2.5 偵測方式字典、§3 等級生命週期（維修驅動的等級升降）、§5 事件帳本資料模型。
> v1.3 變更（實作後回填）：修正 KPOV 筆數為 244、移除不存在的「未評估」計數、現況等級改為應用層推算、
> 修正「惡化中／已改善」的計數定義。

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

### 1.3 v1 不做（Out of Scope）
- 告警事件次數統計與趨勢圖（資料已具備，UI 未定義）
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
- **REQ-LIFE-04** IMPROVE 事件的生效時間依序取：`改善生效日`欄位（若來源新增此欄）→ 否則取**匯入批次時間**。
  > ⚠ **不得使用 `修復時間`**。現有資料中 `修復時間` 僅比 `測試時間` 晚約 30 分鐘，那是 touchup 的完工時間，不是「鎖付角度 DOE 優化」這類改善措施的生效時間。見 D-03。
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

Base: `/api/v1`。所有統計端點共用參數 `view=current|baseline|target`（預設 `current`）、`station`、`line`（皆可多值，逗號分隔）。

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

### 8.1 版面

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

- **REQ-UI-16** 頁首「口徑」切換：`現況` / `基準` / `目標`，**預設現況**。切換即時重算象限圖與柱狀圖。
- **REQ-UI-17** 現況口徑下，若某象限的數字與基準不同，在該格角落標示差異徽章：`▲+1` / `▼-1`（綠降紅升，依 §2.6 排序判定顏色）。
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
- **REQ-UI-07** 兩個下拉：`CTP 站別`、`線別`。**不設「選擇設備」下拉**（站別與設備 1:1，無資訊量）。
- **REQ-UI-08** 皆多選，預設「全部」，站別與線別為 AND。
- **REQ-UI-09** 篩選狀態與口徑切換皆同步到 URL query string。

### 8.5 柱狀圖（REQ-UI-10 ~ 12）
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

---

## 10. 技術選型

| 層 | 選擇 | 理由 |
|---|---|---|
| 前端 | React 18 + TypeScript + Vite | 象限圖用手寫 inline SVG（版面固定，不需圖表庫） |
| 圖表 | 象限圖：inline SVG；柱狀圖：Recharts | |
| 樣式 | Tailwind CSS | |
| 後端 | Python 3.12 + FastAPI + Pydantic | 與 openpyxl 同生態，Excel 處理最順 |
| ORM | SQLAlchemy 2.0 + Alembic | 需要 `LATERAL` 與 ENUM，PostgreSQL 為主要目標 |
| DB | PostgreSQL 16 | `v_kpov_current` 用到 LATERAL；若降 SQLite 需改寫該視圖 |
| 部署 | Docker Compose（nginx + api + db） | 內網單機即可起 |

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
