"""資料模型 — 對應 spec.md §5。

ENUM 以 String + CheckConstraint 實作，確保 SQLite 與 PostgreSQL 行為一致。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

EVENT_TYPES = ("DEGRADE", "IMPROVE")
TRANSITIONS = ("ESCALATED", "IMPROVED", "UNCHANGED")
BATCH_STATUSES = ("pending", "success", "failed")


def _pk() -> Mapped[int]:
    return mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)


class ImportBatch(Base):
    __tablename__ = "import_batch"
    __table_args__ = (CheckConstraint(f"status IN {BATCH_STATUSES}", name="ck_batch_status"),)

    id: Mapped[int] = _pk()
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    imported_by: Mapped[str | None] = mapped_column(Text)
    row_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error_log: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # RBAC（spec §15）：資料集＝一條線的資料，由檔名 WJ<1-8>-<產品廠>-<線別>-數據庫-<MMDD> 解析。
    # 每個 dataset 各自只有一個生效批次；舊資料補為 WJ1-DCS-PM1。
    plant: Mapped[str | None] = mapped_column(String(8))
    factory: Mapped[str | None] = mapped_column(Text)
    line_code: Mapped[str | None] = mapped_column(Text)
    dataset: Mapped[str | None] = mapped_column(Text, index=True)
    data_date: Mapped[str | None] = mapped_column(String(8))


USER_ROLES = ("super_admin", "plant_admin", "user")


class User(Base):
    """系統帳號（spec §15 RBAC）。super_admin 不屬於任何廠（plant 為空）。"""

    __tablename__ = "app_user"
    __table_args__ = (CheckConstraint(f"role IN {USER_ROLES}", name="ck_user_role"),)

    id: Mapped[int] = _pk()
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    plant: Mapped[str | None] = mapped_column(String(8))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 停用、重設密碼時遞增，舊的 JWT 立即失效
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class DimDetectionMethod(Base):
    """偵測方式 ↔ 偵測度分數字典（spec.md §2.5）。"""

    __tablename__ = "dim_detection_method"
    __table_args__ = (CheckConstraint("score BETWEEN 1 AND 10", name="ck_detection_score"),)

    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), primary_key=True)
    method_name: Mapped[str] = mapped_column(Text, primary_key=True)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class DimEquipment(Base):
    __tablename__ = "dim_equipment"

    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), primary_key=True)
    equipment_code: Mapped[str] = mapped_column(Text, primary_key=True)
    equipment_key: Mapped[str | None] = mapped_column(Text)
    production_area: Mapped[str | None] = mapped_column(Text)
    line: Mapped[str | None] = mapped_column(Text)
    model_code: Mapped[str | None] = mapped_column(Text)
    model_desc: Mapped[str | None] = mapped_column(Text)
    equipment_desc: Mapped[str | None] = mapped_column(Text)


class DimErrorCode(Base):
    __tablename__ = "dim_error_code"

    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), primary_key=True)
    error_code: Mapped[str] = mapped_column(Text, primary_key=True)
    alert_category: Mapped[str | None] = mapped_column(Text)
    error_content: Mapped[str | None] = mapped_column(Text)
    breakdown_zh: Mapped[str | None] = mapped_column(Text)
    breakdown_en: Mapped[str | None] = mapped_column(Text)
    module_name: Mapped[str | None] = mapped_column(Text)
    io_signal: Mapped[str | None] = mapped_column(Text)
    component_code: Mapped[str | None] = mapped_column(Text)


class FactKpov(Base):
    """KPOV 基準（spec.md §5.2）。level_baseline 永不因事件變動。"""

    __tablename__ = "fact_kpov"
    __table_args__ = (
        # OP 站沒有設備代碼，且 KPOV 編號會跨站重複（K00001 同時出現在 OP 鎖後蓋與 CTP 各站），
        # 站別本身也不唯一（「鎖銅排」同時是 CTP 站與 OP 站），
        # 因此唯一鍵必須是 屬性1 + 站別 + KPOV 編號。
        UniqueConstraint("batch_id", "attribute1", "station", "kpov_no", name="uq_kpov_identity"),
        Index("ix_kpov_station_level", "batch_id", "attribute1", "station", "level_baseline"),
        Index("ix_kpov_equipment", "batch_id", "equipment_code"),
    )

    id: Mapped[int] = _pk()
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), nullable=False)
    spu_seq: Mapped[str | None] = mapped_column(Text)
    spu_edms: Mapped[str | None] = mapped_column(Text)
    process_category: Mapped[str | None] = mapped_column(Text)
    process_nature: Mapped[str | None] = mapped_column(Text)
    attribute: Mapped[str | None] = mapped_column(Text)
    attribute1: Mapped[str | None] = mapped_column(Text)
    process_unit_zh: Mapped[str | None] = mapped_column(Text)
    process_unit_en: Mapped[str | None] = mapped_column(Text)
    station: Mapped[str] = mapped_column(Text, nullable=False)
    # 新版 KPOV 庫的第一個「站別」欄：站位（輔線 / 自動1 / 人工1 …）
    station_group: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    kpov_name: Mapped[str] = mapped_column(Text, nullable=False)
    kpov_no: Mapped[str | None] = mapped_column(Text)
    alarm_code: Mapped[str | None] = mapped_column(Text)
    equipment_code: Mapped[str | None] = mapped_column(Text)  # OP 站無設備
    small_y_score: Mapped[int | None] = mapped_column(SmallInteger)
    big_y_score: Mapped[int | None] = mapped_column(SmallInteger)
    cc_sc_reason: Mapped[str | None] = mapped_column(Text)
    level_source: Mapped[str | None] = mapped_column(Text)
    level_baseline: Mapped[int | None] = mapped_column(SmallInteger)
    level_mismatch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FactAlarm(Base):
    __tablename__ = "fact_alarm"
    __table_args__ = (Index("ix_alarm_equipment_time", "batch_id", "equipment_code", "stop_start_at"),)

    id: Mapped[int] = _pk()
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), nullable=False)
    period: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    site: Mapped[str | None] = mapped_column(Text)
    production_area: Mapped[str | None] = mapped_column(Text)
    line: Mapped[str | None] = mapped_column(Text)
    model_code: Mapped[str | None] = mapped_column(Text)
    model_desc: Mapped[str | None] = mapped_column(Text)
    model_desc_en: Mapped[str | None] = mapped_column(Text)
    product_category: Mapped[str | None] = mapped_column(Text)
    process_unit: Mapped[str | None] = mapped_column(Text)
    shared_equipment: Mapped[str | None] = mapped_column(Text)
    equipment_code: Mapped[str] = mapped_column(Text, nullable=False)
    equipment_desc: Mapped[str | None] = mapped_column(Text)
    prev_start_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    stop_start_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    stop_end_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    tbs_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    downtime_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    stop_code: Mapped[str | None] = mapped_column(Text)
    stop_duration_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    breakdown_desc: Mapped[str | None] = mapped_column(Text)
    alarm_subcategory: Mapped[str | None] = mapped_column(Text)
    alarm_content: Mapped[str | None] = mapped_column(Text)
    # 鎖附 / 塗覆 / legacy（舊版單一告警表）
    source: Mapped[str | None] = mapped_column(Text)
    kpov_name: Mapped[str | None] = mapped_column(Text)
    kpov_no: Mapped[str | None] = mapped_column(Text)
    serial_no: Mapped[str | None] = mapped_column(Text)


class FactRepair(Base):
    __tablename__ = "fact_repair"

    id: Mapped[int] = _pk()
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), nullable=False)
    month: Mapped[str | None] = mapped_column(Text)
    serial_no: Mapped[str | None] = mapped_column(Text)
    product_model: Mapped[str | None] = mapped_column(Text)
    work_order: Mapped[str | None] = mapped_column(Text)
    line: Mapped[str | None] = mapped_column(Text)
    team: Mapped[str | None] = mapped_column(Text)
    tested_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    defect_desc: Mapped[str | None] = mapped_column(Text)
    product_defect_desc: Mapped[str | None] = mapped_column(Text)
    repair_part_location: Mapped[str | None] = mapped_column(Text)
    responsibility: Mapped[str | None] = mapped_column(Text)
    defect_cause: Mapped[str | None] = mapped_column(Text)
    sub_category: Mapped[str | None] = mapped_column(Text)
    technician: Mapped[str | None] = mapped_column(Text)
    repaired_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    countermeasure: Mapped[str | None] = mapped_column(Text)
    responsible_dept: Mapped[str | None] = mapped_column(Text)
    remark: Mapped[str | None] = mapped_column(Text)
    station: Mapped[str | None] = mapped_column(Text)
    equipment_code: Mapped[str | None] = mapped_column(Text)
    kpov_no: Mapped[str | None] = mapped_column(Text)
    # 「變化後」
    small_y_method_after: Mapped[str | None] = mapped_column(Text)
    big_y_method_after: Mapped[str | None] = mapped_column(Text)
    improvement: Mapped[str | None] = mapped_column(Text)
    # 長期措施：預留，修護報表日後加「長期措施」欄時自動匯入
    long_term_measure: Mapped[str | None] = mapped_column(Text)
    # 「提升後」
    small_y_method_improved: Mapped[str | None] = mapped_column(Text)
    big_y_method_improved: Mapped[str | None] = mapped_column(Text)
    # 來源 Excel 若新增「改善生效日」欄位則填入（spec.md REQ-LIFE-04 / D-03）
    improvement_effective_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # 1019 版起：緊急措施（措施表「緊急措施」欄）
    emergency_measure: Mapped[str | None] = mapped_column(Text)
    emergency_measure_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # 1019 版起：8D 區塊（與客訴報表同結構，欄位加 d8_ 前綴；見 mapping.EIGHT_D_COLUMNS）
    d8_process_unit: Mapped[str | None] = mapped_column(Text)
    d8_big_y_item_before: Mapped[str | None] = mapped_column(Text)
    d8_big_y_method_before: Mapped[str | None] = mapped_column(Text)
    d8_big_y_score_before: Mapped[int | None] = mapped_column(SmallInteger)
    d8_product_kpov: Mapped[str | None] = mapped_column(Text)
    d8_small_y_method_before: Mapped[str | None] = mapped_column(Text)
    d8_small_y_score_before: Mapped[int | None] = mapped_column(SmallInteger)
    d8_level_before: Mapped[int | None] = mapped_column(SmallInteger)
    d8_kpiv_factor_before: Mapped[str | None] = mapped_column(Text)
    d8_kpiv_foolproof_before: Mapped[str | None] = mapped_column(Text)
    d8_kpiv_foolproof_desc_before: Mapped[str | None] = mapped_column(Text)
    d8_kpiv_monitor_before: Mapped[str | None] = mapped_column(Text)
    d8_kpiv_monitor_desc_before: Mapped[str | None] = mapped_column(Text)
    d8_kpiv_level_before: Mapped[str | None] = mapped_column(Text)
    d8_cause_occur: Mapped[str | None] = mapped_column(Text)
    d8_cause_escape: Mapped[str | None] = mapped_column(Text)
    d8_mgmt_verdict: Mapped[str | None] = mapped_column(Text)
    d8_mgmt_measure: Mapped[str | None] = mapped_column(Text)
    d8_tech_ccsc_interception: Mapped[str | None] = mapped_column(Text)
    d8_tech_kpov_design_elimination: Mapped[str | None] = mapped_column(Text)
    d8_tech_kpov_interception: Mapped[str | None] = mapped_column(Text)
    d8_tech_kpiv_foolproof: Mapped[str | None] = mapped_column(Text)
    d8_tech_kpiv_smart: Mapped[str | None] = mapped_column(Text)
    d8_countermeasure: Mapped[str | None] = mapped_column(Text)
    d8_owner: Mapped[str | None] = mapped_column(Text)
    d8_planned_text: Mapped[str | None] = mapped_column(Text)
    d8_done_text: Mapped[str | None] = mapped_column(Text)
    d8_effectiveness: Mapped[str | None] = mapped_column(Text)
    d8_product_kpov_after: Mapped[str | None] = mapped_column(Text)
    d8_small_y_method_after: Mapped[str | None] = mapped_column(Text)
    d8_small_y_score_after: Mapped[int | None] = mapped_column(SmallInteger)
    d8_big_y_item_after: Mapped[str | None] = mapped_column(Text)
    d8_big_y_method_after: Mapped[str | None] = mapped_column(Text)
    d8_big_y_score_after: Mapped[int | None] = mapped_column(SmallInteger)
    d8_level_after: Mapped[int | None] = mapped_column(SmallInteger)
    d8_kpiv_factor_after: Mapped[str | None] = mapped_column(Text)
    d8_kpiv_foolproof_after: Mapped[str | None] = mapped_column(Text)
    d8_kpiv_foolproof_desc_after: Mapped[str | None] = mapped_column(Text)
    d8_kpiv_monitor_after: Mapped[str | None] = mapped_column(Text)
    d8_kpiv_monitor_desc_after: Mapped[str | None] = mapped_column(Text)
    d8_kpiv_level_after: Mapped[str | None] = mapped_column(Text)
    d8_verdict: Mapped[str | None] = mapped_column(Text)
    d8_planned_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    d8_done_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list["FactLevelEvent"]] = relationship(back_populates="repair")


class FactLevelEvent(Base):
    """等級異動帳本（spec.md §5.3）。只增不改。"""

    __tablename__ = "fact_level_event"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "repair_serial", "kpov_no", "equipment_code", "event_type", name="uq_level_event_idempotent"
        ),
        Index("ix_level_event_target", "batch_id", "kpov_no", "equipment_code", "effective_at"),
        CheckConstraint(f"event_type IN {EVENT_TYPES}", name="ck_event_type"),
        CheckConstraint(f"transition IN {TRANSITIONS}", name="ck_transition"),
    )

    id: Mapped[int] = _pk()
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), nullable=False)

    kpov_no: Mapped[str] = mapped_column(Text, nullable=False)
    equipment_code: Mapped[str] = mapped_column(Text, nullable=False)

    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    small_y_method_before: Mapped[str | None] = mapped_column(Text)
    small_y_score_before: Mapped[int | None] = mapped_column(SmallInteger)
    big_y_method_before: Mapped[str | None] = mapped_column(Text)
    big_y_score_before: Mapped[int | None] = mapped_column(SmallInteger)
    level_before: Mapped[int | None] = mapped_column(SmallInteger)

    small_y_method_after: Mapped[str] = mapped_column(Text, nullable=False)
    small_y_score_after: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    big_y_method_after: Mapped[str] = mapped_column(Text, nullable=False)
    big_y_score_after: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    level_after: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    transition: Mapped[str] = mapped_column(String(16), nullable=False)

    repair_id: Mapped[int | None] = mapped_column(ForeignKey("fact_repair.id"))
    repair_serial: Mapped[str | None] = mapped_column(Text)
    defect_desc: Mapped[str | None] = mapped_column(Text)
    improvement: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)

    repair: Mapped[FactRepair | None] = relationship(back_populates="events")


class FactComplaint(Base):
    """客訴報表（8D）。只供顯示與追蹤，不產生等級異動事件。

    以（設備代碼, KPOV 編號）對到 KPOV 庫；來源未填時以（製程單元, 產品KPOV）呈現並標示未對應。
    """

    __tablename__ = "fact_complaint"
    __table_args__ = (Index("ix_complaint_target", "batch_id", "kpov_no", "equipment_code"),)

    id: Mapped[int] = _pk()
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int | None] = mapped_column(Integer)
    # v2.17：序號欄改填產品序號（13 碼英數，例 IOV25C75081W0）時存這裡；填數字流水號時仍存 seq
    serial_no: Mapped[str | None] = mapped_column(Text)
    report_no: Mapped[str | None] = mapped_column(Text)  # 8D 編號
    site: Mapped[str | None] = mapped_column(Text)
    plant: Mapped[str | None] = mapped_column(Text)
    complained_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    customer: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    item: Mapped[str | None] = mapped_column(Text)  # 客訴項目
    process_unit: Mapped[str | None] = mapped_column(Text)
    # 改善前盤查
    big_y_item_before: Mapped[str | None] = mapped_column(Text)
    big_y_method_before: Mapped[str | None] = mapped_column(Text)
    big_y_score_before: Mapped[int | None] = mapped_column(SmallInteger)
    product_kpov: Mapped[str | None] = mapped_column(Text)
    small_y_method_before: Mapped[str | None] = mapped_column(Text)
    small_y_score_before: Mapped[int | None] = mapped_column(SmallInteger)
    level_before: Mapped[int | None] = mapped_column(SmallInteger)
    cause_occur: Mapped[str | None] = mapped_column(Text)
    cause_escape: Mapped[str | None] = mapped_column(Text)
    # 改善對策
    countermeasure: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(Text)
    planned_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    planned_text: Mapped[str | None] = mapped_column(Text)  # 原文（可能多項，例：1.2026/11/3 2.2026/7/30）
    done_text: Mapped[str | None] = mapped_column(Text)
    effectiveness: Mapped[str | None] = mapped_column(Text)
    # 改善後盤查
    small_y_method_after: Mapped[str | None] = mapped_column(Text)
    small_y_score_after: Mapped[int | None] = mapped_column(SmallInteger)
    big_y_method_after: Mapped[str | None] = mapped_column(Text)
    big_y_score_after: Mapped[int | None] = mapped_column(SmallInteger)
    level_after: Mapped[int | None] = mapped_column(SmallInteger)
    verdict: Mapped[str | None] = mapped_column(Text)
    # 改善對策的措施層別（客訴報表 Z–AE 欄；有填內容即視為採用該措施）
    mgmt_measure: Mapped[str | None] = mapped_column(Text)
    tech_ccsc_interception: Mapped[str | None] = mapped_column(Text)
    tech_kpov_design_elimination: Mapped[str | None] = mapped_column(Text)
    tech_kpov_interception: Mapped[str | None] = mapped_column(Text)
    tech_kpiv_foolproof: Mapped[str | None] = mapped_column(Text)
    tech_kpiv_smart: Mapped[str | None] = mapped_column(Text)
    equipment_code: Mapped[str | None] = mapped_column(Text)
    kpov_no: Mapped[str | None] = mapped_column(Text)
    # 1019 版起：8D 區塊補齊的欄位、緊急措施與改善措施／改善時間（長期措施）
    kpiv_factor_before: Mapped[str | None] = mapped_column(Text)
    kpiv_foolproof_before: Mapped[str | None] = mapped_column(Text)
    kpiv_foolproof_desc_before: Mapped[str | None] = mapped_column(Text)
    kpiv_monitor_before: Mapped[str | None] = mapped_column(Text)
    kpiv_monitor_desc_before: Mapped[str | None] = mapped_column(Text)
    kpiv_level_before: Mapped[str | None] = mapped_column(Text)
    mgmt_verdict: Mapped[str | None] = mapped_column(Text)
    product_kpov_after: Mapped[str | None] = mapped_column(Text)
    big_y_item_after: Mapped[str | None] = mapped_column(Text)
    kpiv_factor_after: Mapped[str | None] = mapped_column(Text)
    kpiv_foolproof_after: Mapped[str | None] = mapped_column(Text)
    kpiv_foolproof_desc_after: Mapped[str | None] = mapped_column(Text)
    kpiv_monitor_after: Mapped[str | None] = mapped_column(Text)
    kpiv_monitor_desc_after: Mapped[str | None] = mapped_column(Text)
    kpiv_level_after: Mapped[str | None] = mapped_column(Text)
    emergency_measure: Mapped[str | None] = mapped_column(Text)
    emergency_measure_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    improvement: Mapped[str | None] = mapped_column(Text)
    improvement_effective_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


CHANGE_KINDS = ("PCN", "ECN")


class FactChangeRecord(Base):
    """PCN / ECN 變更紀錄。只供 KPOV 時間軸顯示，不參與等級計算。

    偵測欄位刻意存成文字：PCN 填的是分數（7），ECN 可能填偵測方式名稱。
    ECN 的影響站別、設備ID 常為 NA，代表全廠適用。
    """

    __tablename__ = "fact_change_record"
    __table_args__ = (
        CheckConstraint(f"kind IN {CHANGE_KINDS}", name="ck_change_kind"),
        Index("ix_change_target", "batch_id", "kpov_no", "equipment_code"),
    )

    id: Mapped[int] = _pk()
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    effective_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ecn_no: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    station: Mapped[str | None] = mapped_column(Text)
    equipment_code: Mapped[str | None] = mapped_column(Text)
    kpov_name: Mapped[str | None] = mapped_column(Text)
    kpov_no: Mapped[str | None] = mapped_column(Text)
    small_y_before: Mapped[str | None] = mapped_column(Text)
    big_y_before: Mapped[str | None] = mapped_column(Text)
    level_before: Mapped[str | None] = mapped_column(Text)
    small_y_after: Mapped[str | None] = mapped_column(Text)
    big_y_after: Mapped[str | None] = mapped_column(Text)
    level_after: Mapped[str | None] = mapped_column(Text)


class FactCheckItem(Base):
    """高風險項（Level 3）點檢項目，來源為「高風險項點檢」工作表。

    點檢結果不存這裡：AR 點檢紀錄是連續累積的營運資料，以
    (設備代碼, KPOV 編號, 點檢內容) 自然鍵對到這裡的項目，跨批次不斷裂。
    """

    __tablename__ = "fact_check_item"
    __table_args__ = (Index("ix_check_item_equipment", "batch_id", "equipment_code"),)

    id: Mapped[int] = _pk()
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id", ondelete="CASCADE"), nullable=False)
    station: Mapped[str | None] = mapped_column(Text)
    attribute1: Mapped[str | None] = mapped_column(Text)
    kpov_name: Mapped[str | None] = mapped_column(Text)
    kpov_no: Mapped[str | None] = mapped_column(Text)
    equipment_code: Mapped[str | None] = mapped_column(Text)
    small_y_score: Mapped[int | None] = mapped_column(SmallInteger)
    big_y_score: Mapped[int | None] = mapped_column(SmallInteger)
    level_source: Mapped[str | None] = mapped_column(Text)
    check_content: Mapped[str] = mapped_column(Text, nullable=False)
    # 1019 版起：KPIV(x) 管控等級，例「A: 防呆防錯+智能」「B: 防呆防錯+人工」
    kpiv_control_level: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str | None] = mapped_column(Text)
    interval_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=2)


# ---------------------------------------------------------------------------
# AR 設備點檢（整合自 webXR-test，見 ar-integration-spec.md §6）
# ---------------------------------------------------------------------------

AR_STATUSES = ("ok", "warn")


class ArDevice(Base):
    """AR marker 對應的設備。

    刻意不掛 batch_id：品控力的維度表是批次式的（每次匯入 Excel 建新批次），
    AR 的設備與點檢紀錄則是連續累積的營運資料，不隨匯入批次更替。
    """

    __tablename__ = "ar_device"
    __table_args__ = (
        CheckConstraint("marker_id BETWEEN 0 AND 63", name="ck_ar_marker_range"),
    )

    # AR.js 3x3 barcode marker，有效值 0~63
    marker_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    work_instruction: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)  # 相對路徑，例 /api/ar/uploads/x.jpg

    # 橋接品控力設備主檔。刻意「不」建外鍵：dim_equipment 的主鍵是
    # (batch_id, equipment_code)，每次匯入都會產生新的一組；建外鍵會把 AR 設備
    # 綁死在某個匯入批次上，下次匯入就斷裂。查詢時 join 當前 active 批次即可。
    equipment_code: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )

    inspections: Mapped[list["ArInspection"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class ArInspection(Base):
    """一次點檢紀錄。"""

    __tablename__ = "ar_inspection"
    __table_args__ = (
        CheckConstraint(f"status IN {AR_STATUSES}", name="ck_ar_status"),
        Index("ix_ar_inspection_device_time", "marker_id", "inspected_at"),
    )

    id: Mapped[int] = _pk()
    marker_id: Mapped[int] = mapped_column(
        ForeignKey("ar_device.marker_id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    inspected_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    # 逐項點檢（高風險項點檢）：以自然鍵對到 fact_check_item；三者皆空 = 整台設備點檢
    equipment_code: Mapped[str | None] = mapped_column(Text)
    kpov_no: Mapped[str | None] = mapped_column(Text)
    check_content: Mapped[str | None] = mapped_column(Text)

    device: Mapped[ArDevice] = relationship(back_populates="inspections")


class CheckPhotoInspection(Base):
    """拍照點檢：上傳照片即視為完成一次高風險項點檢（免掃 AR marker）。

    不併入 ar_inspection：該表的 marker_id 是 NOT NULL 外鍵，拍照點檢沒有 marker。
    與 ar_inspection 的逐項紀錄一樣，以 (設備代碼, KPOV 編號, 點檢內容) 自然鍵對到
    fact_check_item，跨匯入批次不斷裂。
    """

    __tablename__ = "check_photo_inspection"
    __table_args__ = (
        CheckConstraint(f"status IN {AR_STATUSES}", name="ck_check_photo_status"),
        Index("ix_check_photo_item_time", "equipment_code", "inspected_at"),
    )

    id: Mapped[int] = _pk()
    equipment_code: Mapped[str] = mapped_column(Text, nullable=False)
    kpov_no: Mapped[str | None] = mapped_column(Text)
    check_content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="ok")
    note: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str] = mapped_column(Text, nullable=False)
    # 所屬資料集（一條線）；不同廠可能有相同的設備代碼
    dataset: Mapped[str | None] = mapped_column(Text)
    inspected_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    # 緊急措施（v2.15）：點檢後由工程師在點檢看板補填，可修改；記錄最後修改人與時間
    emergency_measure: Mapped[str | None] = mapped_column(Text)
    emergency_measure_by: Mapped[str | None] = mapped_column(Text)
    emergency_measure_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class CheckCountImport(Base):
    """匯入的歷史點檢結果（spec §19）：只用來累加點檢看板站別卡片的正常／異常次數，不出現在點檢紀錄。

    重新部署後拍照點檢紀錄會歸零，由最高權限管理者把舊系統匯出的點檢紀錄 Excel 匯入補回數量。
    以（資料集, 設備代碼, 點檢內容, 點檢時間）去重：同一份檔案重複匯入、或與系統內的拍照點檢重疊都不會重算。
    """

    __tablename__ = "check_count_import"
    __table_args__ = (
        CheckConstraint(f"status IN {AR_STATUSES}", name="ck_check_count_import_status"),
        UniqueConstraint("dataset", "equipment_code", "check_content", "inspected_at", name="uq_check_count_import_row"),
    )

    id: Mapped[int] = _pk()
    dataset: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    equipment_code: Mapped[str] = mapped_column(Text, nullable=False)
    station: Mapped[str | None] = mapped_column(Text)
    check_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    inspected_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str | None] = mapped_column(Text)  # 匯入的檔名
    imported_by: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )


SOLUTION_TYPES = ("technical", "management")
TECH_TARGETS = ("KPOV", "KPIV")


class EmergencyMeasure(Base):
    """高風險異動的緊急措施分類（使用者在等級異動總覽填寫）。

    不掛 batch_id：這是使用者輸入的資料，重新匯入 Excel 不可洗掉。
    以（維修序號, KPOV 編號, 設備代碼）自然鍵對到修護報表的那一筆維修。
    技術解／管理解二選一；技術解再分 KPOV（設計消除、設備攔截）或 KPIV（防呆防錯、智能監控）。
    """

    __tablename__ = "emergency_measure"
    __table_args__ = (
        UniqueConstraint("repair_serial", "kpov_no", "equipment_code", name="uq_emergency_measure_target"),
        CheckConstraint(f"solution_type IN {SOLUTION_TYPES}", name="ck_emergency_solution_type"),
        CheckConstraint(
            f"tech_target IS NULL OR tech_target IN {TECH_TARGETS}", name="ck_emergency_tech_target"
        ),
    )

    id: Mapped[int] = _pk()
    repair_serial: Mapped[str] = mapped_column(Text, nullable=False)
    kpov_no: Mapped[str] = mapped_column(Text, nullable=False)
    equipment_code: Mapped[str] = mapped_column(Text, nullable=False)
    solution_type: Mapped[str] = mapped_column(String(16), nullable=False)
    tech_target: Mapped[str | None] = mapped_column(String(8))
    design_elimination: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    equipment_interception: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    foolproof: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    smart_monitoring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    management_note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
    )

