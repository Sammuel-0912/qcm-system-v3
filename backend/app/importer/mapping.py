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
    "kpov": ("KPOV库-by 站", "KPOV庫-by 站", "KPOV库", "KPOV庫"),
    "repair": ("修護報表", "修护报表"),
    "equipment": ("Dim_Equipment",),
    "alarm": ("7_8月設備告警", "設備告警(與品質相關)", "設備告警"),
    "error_code": ("設備告警品質相關代碼庫",),
    # 與 error_code 內容重複，刻意忽略（REQ-IMP-04）
    "error_code_dup": ("與品質相關設M-error庫",),
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
}
ALARM_REQUIRED = ("設備代碼",)

REPAIR_COLUMNS: dict[str, str] = {
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
    "設備ID": "equipment_code",
    "KPOV 编号": "kpov_no",
    "小y偵測方式(變化後)": "small_y_method_after",
    "大y偵測方式(變化後)": "big_y_method_after",
    "改善措施": "improvement",
    "小y偵測方式(提升後)": "small_y_method_improved",
    "大y偵測方式(提升後)": "big_y_method_improved",
    # D-03：來源 Excel 若新增此欄則自動採用為 IMPROVE 生效時間
    "改善生效日": "improvement_effective_at",
}
REPAIR_REQUIRED = ("設備ID", "KPOV 编号")

# 數值欄位（需轉 int / float）
INT_FIELDS = {"small_y_score", "big_y_score"}
FLOAT_FIELDS = {"tbs_min", "downtime_min", "stop_duration_min"}
DATETIME_FIELDS = {
    "prev_start_at",
    "stop_start_at",
    "stop_end_at",
    "tested_at",
    "repaired_at",
    "improvement_effective_at",
}
