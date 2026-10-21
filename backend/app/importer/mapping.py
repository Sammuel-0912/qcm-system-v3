"""工作表與欄位名稱對應 — spec.md §6。

匯入一律以「名稱」定位，不依賴工作表順序或欄位位置（REQ-IMP-01 / REQ-IMP-02），
因為來源檔經過 Power Query 處理，欄位會增減。
"""
from __future__ import annotations

import re

_NOISE = re.compile(r"_x000D_|\r|\n")


def normalize(value) -> str:
    """表頭正規化：去除 Excel 殘留的 _x000D_、換行與前後空白。"""
    if value is None:
        return ""
    return _NOISE.sub(" ", str(value)).strip()


# 工作表角色 -> 名稱比對前綴（皆以 normalize 後比對）
SHEET_PREFIXES: dict[str, tuple[str, ...]] = {
    # 新版（1008）工作表名稱為「KPOV-by 站 」，沒有「库/庫」
    "kpov": ("KPOV库-by 站", "KPOV庫-by 站", "KPOV-by 站", "KPOV库", "KPOV庫"),
    "repair": ("修護報表", "修护报表"),
    "equipment": ("Dim_Equipment",),
    # 新版以「設備對應參考」取代 Dim_Equipment（含 OP 人工站 A0001–A0008）
    "equipment_ref": ("設備對應參考",),
    "alarm": ("7_8月設備告警", "設備告警(與品質相關)"),
    "alarm_screw": ("鎖附設備告警",),
    "alarm_coat": ("塗覆設備告警",),
    "error_code": ("設備告警品質相關代碼庫",),
    # 與 error_code 內容重複，刻意忽略（REQ-IMP-04）
    "error_code_dup": ("與品質相關設M-error庫",),
    "pcn": ("PCN 紀錄", "PCN紀錄"),
    "ecn": ("ECN 紀錄", "ECN紀錄"),
    "check_item": ("高風險項點檢",),
    "complaint": ("客訴報表",),
}

KPOV_COLUMNS: dict[str, str] = {
    "SPU流水號": "spu_seq",
    "SPU (EDMS)": "spu_edms",
    "製程類別": "process_category",
    "製程性質": "process_nature",
    "屬性": "attribute",
    "屬性1": "attribute1",
    "製程單元_繁體": "process_unit_zh",
    "製程單元_英文": "process_unit_en",
    # 新版有兩個「站別」：第一個是站位（輔線/自動1/人工1），最後一個才是原站別，
    # 由 excel._read_table 的 duplicates 參數分配
    "站別": "station",
    "分类": "category",
    "KPOV": "kpov_name",
    "KPOV 编号": "kpov_no",
    "設備告警代碼": "alarm_code",
    "設備ID": "equipment_code",
    "小y偵測度": "small_y_score",
    "大Y偵測度": "big_y_score",
    "CC/SC原因": "cc_sc_reason",
    "品控力等級": "level_source",
}
KPOV_REQUIRED = ("站別", "KPOV", "設備ID", "小y偵測度", "大Y偵測度")

EQUIPMENT_COLUMNS: dict[str, str] = {
    "EquipmentKey": "equipment_key",
    "生產區域": "production_area",
    "線別": "line",
    "設備型號": "model_code",
    "設備型號描述": "model_desc",
    "設備代碼": "equipment_code",
    "設備描述": "equipment_desc",
}
EQUIPMENT_REQUIRED = ("設備代碼", "線別")

ERROR_CODE_COLUMNS: dict[str, str] = {
    "設備錯誤碼": "error_code",
    "警報分類（中文）": "alert_category",
    "錯誤内容（中文）": "error_content",
    "故障現象描述（中文）": "breakdown_zh",
    "故障現象描述（英文）": "breakdown_en",
    "報錯模組名稱": "module_name",
    "警報觸發對應IO": "io_signal",
    "元件代碼": "component_code",
}
ERROR_CODE_REQUIRED = ("設備錯誤碼",)

ALARM_COLUMNS: dict[str, str] = {
    "日期": "period",
    "地區": "region",
    "廠區": "site",
    "生產區域": "production_area",
    "線別": "line",
    "設備型號": "model_code",
    "設備型號描述": "model_desc",
    "設備型號英文描述": "model_desc_en",
    "產品類別": "product_category",
    "製程單元": "process_unit",
    "通共用設備": "shared_equipment",
    "設備代碼": "equipment_code",
    "設備描述": "equipment_desc",
    "前次啟動時間": "prev_start_at",
    "當次停頓時間": "stop_start_at",
    "當次停頓結束時間": "stop_end_at",
    "TBS(分)": "tbs_min",
    "關機時長(分)": "downtime_min",
    "停頓代碼": "stop_code",
    "停頓時長(分)": "stop_duration_min",
    "故障現象": "breakdown_desc",
    "報警次分類": "alarm_subcategory",
    "報警內容": "alarm_content",
    "KPOV": "kpov_name",
    "KPOV 编号": "kpov_no",
}
ALARM_REQUIRED = ("設備代碼",)

# 「塗覆設備告警」是維修單格式，對應到同一張告警表
ALARM_COATING_COLUMNS: dict[str, str] = {
    "序號": "serial_no",
    "線別": "line",
    "測試時間": "stop_start_at",
    "不良描述": "alarm_content",
    "產品不良描述": "breakdown_desc",
    "制程單元": "process_unit",
    "設備ID": "equipment_code",
    "KPOV": "kpov_name",
    "KPOV 编号": "kpov_no",
}
ALARM_COATING_REQUIRED = ("設備ID", "KPOV 编号")

_REPAIR_COMMON: dict[str, str] = {
    "月份": "month",
    "序號": "serial_no",
    "機種": "product_model",
    "工單": "work_order",
    "線別": "line",
    "組別": "team",
    "測試時間": "tested_at",
    "不良描述": "defect_desc",
    "產品不良描述": "product_defect_desc",
    "維修零件位置": "repair_part_location",
    "責任分類": "responsibility",
    "不良原因": "defect_cause",
    "小分類": "sub_category",
    "維修人員": "technician",
    "修復時間": "repaired_at",
    "處理對策": "countermeasure",
    "責任部門": "responsible_dept",
    "維修備註": "remark",
    "站別": "station",
    "設備ID": "equipment_code",
    "KPOV 编号": "kpov_no",
    "改善措施": "improvement",
    # 預留：修護報表日後加「長期措施」欄時自動匯入
    "長期措施": "long_term_measure",
    # D-03：IMPROVE 生效時間。1011 版起修護報表提供「改善時間」
    "改善時間": "improvement_effective_at",
    "改善生效日": "improvement_effective_at",
    # 1019 版起：緊急措施（措施表「緊急措施」欄，紅字時間為緊急措施時間）
    "緊急措施": "emergency_measure",
    "緊急措施時間": "emergency_measure_at",
}

# 舊版：「(變化後)」= 不良發生時（DEGRADE）、「(提升後)」= 改善後（IMPROVE）
REPAIR_COLUMNS: dict[str, str] = {
    **_REPAIR_COMMON,
    "小y偵測方式(變化後)": "small_y_method_after",
    "大y偵測方式(變化後)": "big_y_method_after",
    "小y偵測方式(提升後)": "small_y_method_improved",
    "大y偵測方式(提升後)": "big_y_method_improved",
}

# 新版（1008）：無後綴 = 不良發生時（DEGRADE）、「(變化後)」= 改善後（IMPROVE）。
# 同名的「(變化後)」在兩版意義相反，因此以是否存在「(提升後)」欄判別版本。
# 分數欄只用來與偵測方式字典比對，不入庫。
REPAIR_COLUMNS_V2: dict[str, str] = {
    **_REPAIR_COMMON,
    "小y偵測方式": "small_y_method_after",
    "大y偵測方式": "big_y_method_after",
    "小y偵測方式(變化後)": "small_y_method_improved",
    "大y偵測方式(變化後)": "big_y_method_improved",
    "小y分數": "_small_y_score_after",
    "大y分數": "_big_y_score_after",
    "小y分數(變化後)": "_small_y_score_improved",
    "大y分數(變化後)": "_big_y_score_improved",
}
REPAIR_V1_MARKER = "(提升後)"
REPAIR_REQUIRED = ("KPOV 编号",)

# 「設備對應參考」：左區 CTP（MES站別/站別/屬性/設備名稱/設備ID）、右區 OP（站別/屬性/設備名稱/設備代碼）
EQUIPMENT_REF_NAME = "設備名稱"
EQUIPMENT_REF_CODES = ("設備ID", "設備代碼")

# CTP 站別 -> 設備代碼的強制修正。來源資料曾把「鎖銅排」的設備誤植為 OT00420104
# （鎖電感的設備），現場確認鎖銅排是 OT00420118。
# 以站別名稱為鍵而非站位：1011 版起「自動3／自動4」的站位標籤對調過，站別名稱才穩定。
EQUIPMENT_OVERRIDES: dict[str, str] = {"鎖銅排": "OT00420118"}

# OP 人工站設備對照（使用者確認的「設備對應參考」OP 區）。1011 版的 Excel 移除了這一區，
# 空資料庫直接匯入時以此為預設；檔案若有提供則以檔案為準。
DEFAULT_OP_EQUIPMENT: tuple[tuple[str, str, str], ...] = (
    ("人工一", "插線/理線", "A0001"),
    ("人工二", "固定散熱片", "A0002"),
    ("人工三", "鎖後蓋", "A0003"),
    ("人工四", "固定銅排/ 電感", "A0004"),
    ("人工五", "固定保險絲/軟銅排", "A0005"),
    ("人工六", "軟銅排1", "A0006"),
    ("人工七", "固定絕緣片/PWB板", "A0007"),
    ("人工八", "鎖PWB板", "A0008"),
)

# 只用於 OP（人工站）的站別別名：高風險項點檢等表沿用舊站名，對不到「設備對應參考」
STATION_ALIASES_OP: dict[str, str] = {
    "固定絕緣片": "固定絕緣片/PWB板",
    "鎖軟銅排2": "固定保險絲/軟銅排",
}

# PCN / ECN：「切入前」「切入後」兩組同名欄位，依出現順序分配 before / after
CHANGE_COLUMNS: dict[str, str] = {
    "切入時間": "effective_at",
    "ECN號碼": "ecn_no",
    "內容": "content",
    "影響站別": "station",
    "設備ID": "equipment_code",
    "KPOV": "kpov_name",
    "KPOV 编号": "kpov_no",
    "小y偵測方式": "small_y",
    "大y偵測方式": "big_y",
    "品控力等級": "level",
}
CHANGE_PAIRED = ("small_y", "big_y", "level")
CHANGE_REQUIRED = ("切入時間", "內容")

# 客訴報表：三層合併表頭，同名欄位（偵測方式、偵測度、簡述作業方式…）重複多次，
# 無法以名稱對應，改以欄位位置對應；匯入時再以 COMPLAINT_HEADER_CHECKS 驗證表頭文字，
# 來源檔欄位若有增減會直接報錯，而不是默默讀錯欄。
# 8D 區塊（現狀盤查 → 原因 → 改善對策 → 改善後盤查）。客訴報表在 I–AX，1019 版的修護報表
# 也加入同一段，位置整段右移 11 欄（T–BI）。欄位字母以客訴報表為準，修護報表用 shift_letter 換算。
EIGHT_D_COLUMNS: dict[str, str] = {
    "I": "process_unit",
    # 現狀：Y（CC/SC）與 y（KPOV）的攔截能力
    "J": "big_y_item_before",
    "K": "big_y_method_before",
    "L": "big_y_score_before",
    "M": "product_kpov",
    "N": "small_y_method_before",
    "O": "small_y_score_before",
    "P": "level_before",
    # 現狀：關鍵 KPIV(x) 管控力
    "Q": "kpiv_factor_before",
    "R": "kpiv_foolproof_before",
    "S": "kpiv_foolproof_desc_before",
    "T": "kpiv_monitor_before",
    "U": "kpiv_monitor_desc_before",
    "V": "kpiv_level_before",
    "W": "cause_occur",
    "X": "cause_escape",
    # 改善對策：管理解（流程卡控）與技術解（CC/SC 設備攔截；KPOV 設計消除／設備攔截；KPIV 防呆防錯／智能監控）
    "Y": "mgmt_verdict",
    "Z": "mgmt_measure",
    "AA": "tech_ccsc_interception",
    "AB": "tech_kpov_design_elimination",
    "AC": "tech_kpov_interception",
    "AD": "tech_kpiv_foolproof",
    "AE": "tech_kpiv_smart",
    "AF": "countermeasure",
    "AG": "owner",
    "AH": "planned_text",
    "AI": "done_text",
    "AJ": "effectiveness",
    # 改善後
    "AK": "product_kpov_after",
    "AL": "small_y_method_after",
    "AM": "small_y_score_after",
    "AN": "big_y_item_after",
    "AO": "big_y_method_after",
    "AP": "big_y_score_after",
    "AQ": "level_after",
    "AR": "kpiv_factor_after",
    "AS": "kpiv_foolproof_after",
    "AT": "kpiv_foolproof_desc_after",
    "AU": "kpiv_monitor_after",
    "AV": "kpiv_monitor_desc_after",
    "AW": "kpiv_level_after",
    "AX": "verdict",
}
EIGHT_D_INT_FIELDS = ("big_y_score_before", "small_y_score_before", "small_y_score_after", "big_y_score_after")
EIGHT_D_LEVEL_FIELDS = ("level_before", "level_after")
# 驗證 8D 區塊位置的表頭文字（客訴報表欄位）
EIGHT_D_HEADER_CHECKS: dict[str, str] = {
    "I": "製程單元",
    "M": "產品KPOV",
    "P": "品質管控力",
    "Z": "管理對策",
    "AF": "改善對策總結",
    "AG": "責任人",
    "AH": "預計完成時間",
    "AI": "實際完成時間",
    "AQ": "品質管控力",
    "AX": "改善判定",
}
# 修護報表的 8D 區塊比客訴報表右移 11 欄；8D 欄位在 fact_repair 一律加 d8_ 前綴，
# 避免與維修本身的欄位（處理對策 countermeasure、變化後偵測方式 small_y_method_after…）撞名
REPAIR_EIGHT_D_OFFSET = 11
REPAIR_EIGHT_D_PREFIX = "d8_"


def shift_letter(letter: str, offset: int) -> str:
    from openpyxl.utils import column_index_from_string, get_column_letter

    return get_column_letter(column_index_from_string(letter) + offset)


COMPLAINT_COLUMNS: dict[str, str] = {
    "A": "seq",
    "B": "report_no",
    "C": "site",
    "D": "plant",
    "E": "complained_at",
    "F": "customer",
    "G": "category",
    "H": "item",
    **EIGHT_D_COLUMNS,
    "AY": "equipment_code",
    "AZ": "kpov_no",
}
COMPLAINT_HEADER_CHECKS: dict[str, str] = {
    "A": "序號",
    "B": "8D編號",
    "E": "日期",
    "H": "客訴項目",
    **EIGHT_D_HEADER_CHECKS,
    "AY": "設備ID",
    "AZ": "KPOV編號",
}
# 1019 版起：客訴報表在 KPOV 編號右側插入緊急措施；位置可能再變動，改以表頭文字找欄位
COMPLAINT_NAMED_COLUMNS: dict[str, str] = {
    "緊急措施": "emergency_measure",
    "緊急措施時間": "emergency_measure_at",
    "改善時間": "improvement_effective_at",
    "改善措施": "improvement",
}
COMPLAINT_HEADER_ROWS = 6  # 表頭最多在前 6 列內

CHECK_ITEM_COLUMNS: dict[str, str] = {
    "屬性1": "attribute1",
    "站別": "station",
    "KPOV": "kpov_name",
    "KPOV 编号": "kpov_no",
    "設備ID": "equipment_code",
    "小y偵測度": "small_y_score",
    "大Y偵測度": "big_y_score",
    "品控力等級": "level_source",
    "點檢內容": "check_content",
    # 1019 版起：點檢內容改稱「KPIV(x) 點檢內容」，並新增 KPIV 管控等級（A/B/E…）
    "KPIV(x) 點檢內容": "check_content",
    "KPIV(x) 管控等級": "kpiv_control_level",
    "點檢頻率": "frequency",
}
# 「A|B」表示兩個表頭擇一即可
CHECK_ITEM_REQUIRED = ("KPOV 编号", "KPIV(x) 點檢內容|點檢內容")

# 數值欄位（需轉 int / float）
INT_FIELDS = {"small_y_score", "big_y_score"}
FLOAT_FIELDS = {"tbs_min", "downtime_min", "stop_duration_min"}
DATETIME_FIELDS = {
    "effective_at",
    "prev_start_at",
    "stop_start_at",
    "stop_end_at",
    "tested_at",
    "repaired_at",
    "improvement_effective_at",
    "emergency_measure_at",
}
