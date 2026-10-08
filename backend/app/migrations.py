"""輕量結構遷移。

`Base.metadata.create_all()` 只會建立不存在的表，**永遠不會修改已存在的表**。
因此支援 OP 站別所需的兩項變更（equipment_code 改為可空、唯一鍵改為
屬性1+站別+KPOV編號）不會自動套用到既有資料庫，匯入 OP 資料時會撞
NOT NULL 而整批失敗。

這裡以冪等的方式補上，SQLite 與 PostgreSQL 皆適用，且不動既有資料。
"""
from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect, text

log = logging.getLogger(__name__)

OLD_UNIQUE = "uq_kpov_equipment"
NEW_UNIQUE = "uq_kpov_identity"


def _kpov_equipment_is_required(engine: Engine) -> bool:
    inspector = inspect(engine)
    if "fact_kpov" not in inspector.get_table_names():
        return False
    for column in inspector.get_columns("fact_kpov"):
        if column["name"] == "equipment_code":
            return not column["nullable"]
    return False


def _has_constraint(engine: Engine, name: str) -> bool:
    inspector = inspect(engine)
    if "fact_kpov" not in inspector.get_table_names():
        return False
    names = {c.get("name") for c in inspector.get_unique_constraints("fact_kpov")}
    names |= {i.get("name") for i in inspector.get_indexes("fact_kpov")}
    return name in names


def _migrate_postgres(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE fact_kpov ALTER COLUMN equipment_code DROP NOT NULL"))
        conn.execute(text(f"ALTER TABLE fact_kpov DROP CONSTRAINT IF EXISTS {OLD_UNIQUE}"))
        conn.execute(
            text(
                f"ALTER TABLE fact_kpov ADD CONSTRAINT {NEW_UNIQUE} "
                "UNIQUE (batch_id, attribute1, station, kpov_no)"
            )
        )


def _migrate_sqlite(engine: Engine) -> None:
    """SQLite 無法 ALTER 既有欄位的 NOT NULL，必須重建表再搬資料。"""
    columns = [c["name"] for c in inspect(engine).get_columns("fact_kpov")]
    col_list = ", ".join(columns)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("ALTER TABLE fact_kpov RENAME TO fact_kpov__old"))
        conn.execute(
            text(
                """
                CREATE TABLE fact_kpov (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  batch_id INTEGER NOT NULL REFERENCES import_batch(id) ON DELETE CASCADE,
                  spu_seq TEXT, spu_edms TEXT, process_category TEXT, process_nature TEXT,
                  attribute TEXT, attribute1 TEXT, process_unit_zh TEXT, process_unit_en TEXT,
                  station TEXT NOT NULL, category TEXT, kpov_name TEXT NOT NULL, kpov_no TEXT,
                  alarm_code TEXT,
                  equipment_code TEXT,
                  small_y_score SMALLINT, big_y_score SMALLINT, cc_sc_reason TEXT,
                  level_source TEXT, level_baseline SMALLINT,
                  level_mismatch BOOLEAN NOT NULL DEFAULT 0,
                  CONSTRAINT uq_kpov_identity UNIQUE (batch_id, attribute1, station, kpov_no)
                )
                """
            )
        )
        conn.execute(text(f"INSERT INTO fact_kpov ({col_list}) SELECT {col_list} FROM fact_kpov__old"))
        conn.execute(text("DROP TABLE fact_kpov__old"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_kpov_station_level "
                "ON fact_kpov (batch_id, attribute1, station, level_baseline)"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_kpov_equipment ON fact_kpov (batch_id, equipment_code)")
        )
        conn.execute(text("PRAGMA foreign_keys=ON"))


# 後來新增、皆可空的欄位：(表, 欄位, 型別)。既有資料庫以 ADD COLUMN 補上。
ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("fact_kpov", "station_group", "TEXT"),
    ("fact_alarm", "source", "TEXT"),
    ("fact_alarm", "kpov_name", "TEXT"),
    ("fact_alarm", "kpov_no", "TEXT"),
    ("fact_alarm", "serial_no", "TEXT"),
    ("fact_repair", "station", "TEXT"),
    ("ar_inspection", "equipment_code", "TEXT"),
    ("ar_inspection", "kpov_no", "TEXT"),
    ("ar_inspection", "check_content", "TEXT"),
)


def _add_missing_columns(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    applied: list[str] = []
    for table, column, sql_type in ADDED_COLUMNS:
        if table not in tables:
            continue
        existing = {c["name"] for c in inspect(engine).get_columns(table)}
        if column in existing:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
        applied.append(f"{table}.{column} 新增欄位")
    return applied


def ensure_schema(engine: Engine) -> list[str]:
    """把既有資料庫補到目前的結構。回傳做過的動作，供啟動時記錄。"""
    applied: list[str] = []

    if _kpov_equipment_is_required(engine):
        if engine.dialect.name == "postgresql":
            _migrate_postgres(engine)
        elif engine.dialect.name == "sqlite":
            _migrate_sqlite(engine)
        else:  # pragma: no cover - 其他方言未支援
            raise RuntimeError(
                f"需要手動遷移 fact_kpov.equipment_code 為可空（方言：{engine.dialect.name}）"
            )
        applied.append("fact_kpov.equipment_code 改為可空（支援無設備的 OP 站別）")
        applied.append(f"唯一鍵 {OLD_UNIQUE} -> {NEW_UNIQUE}（屬性1 + 站別 + KPOV編號）")
    elif _has_constraint(engine, OLD_UNIQUE) and not _has_constraint(engine, NEW_UNIQUE):
        if engine.dialect.name == "postgresql":
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE fact_kpov DROP CONSTRAINT IF EXISTS {OLD_UNIQUE}"))
                conn.execute(
                    text(
                        f"ALTER TABLE fact_kpov ADD CONSTRAINT {NEW_UNIQUE} "
                        "UNIQUE (batch_id, attribute1, station, kpov_no)"
                    )
                )
            applied.append(f"唯一鍵 {OLD_UNIQUE} -> {NEW_UNIQUE}")

    # 必須在 fact_kpov 重建之後：重建用的是固定的舊欄位清單
    applied.extend(_add_missing_columns(engine))

    for action in applied:
        log.warning("結構遷移：%s", action)
    return applied
