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
    equipment_code: Mapped[str | None] = mapped_column(Text)
    kpov_no: Mapped[str | None] = mapped_column(Text)
    # 「變化後」
    small_y_method_after: Mapped[str | None] = mapped_column(Text)
    big_y_method_after: Mapped[str | None] = mapped_column(Text)
    improvement: Mapped[str | None] = mapped_column(Text)
    # 「提升後」
    small_y_method_improved: Mapped[str | None] = mapped_column(Text)
    big_y_method_improved: Mapped[str | None] = mapped_column(Text)
    # 來源 Excel 若新增「改善生效日」欄位則填入（spec.md REQ-LIFE-04 / D-03）
    improvement_effective_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

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
