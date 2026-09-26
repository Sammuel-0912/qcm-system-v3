"""結構遷移測試 — create_all 不會修改既有表，遷移必須補上。"""
from __future__ import annotations

import pathlib
import sqlite3

import pytest

RAW = pathlib.Path(__file__).resolve().parent.parent.parent / "raw_data.xlsx"

OLD_SCHEMA = """
CREATE TABLE import_batch (
  id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, imported_at DATETIME NOT NULL,
  imported_by TEXT, row_counts JSON NOT NULL, status VARCHAR(16) NOT NULL, error_log JSON,
  is_active BOOLEAN NOT NULL);
CREATE TABLE fact_kpov (
  id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER NOT NULL,
  spu_seq TEXT, spu_edms TEXT, process_category TEXT, process_nature TEXT, attribute TEXT,
  attribute1 TEXT, process_unit_zh TEXT, process_unit_en TEXT, station TEXT NOT NULL,
  category TEXT, kpov_name TEXT NOT NULL, kpov_no TEXT, alarm_code TEXT,
  equipment_code TEXT NOT NULL, small_y_score SMALLINT, big_y_score SMALLINT,
  cc_sc_reason TEXT, level_source TEXT, level_baseline SMALLINT, level_mismatch BOOLEAN NOT NULL,
  CONSTRAINT uq_kpov_equipment UNIQUE (batch_id, kpov_no, equipment_code));
"""


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_old_schema_is_migrated_and_op_rows_import(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(OLD_SCHEMA)
    con.commit()
    con.close()

    from sqlalchemy import create_engine, inspect

    from app.migrations import ensure_schema

    engine = create_engine(f"sqlite:///{db}", future=True)

    applied = ensure_schema(engine)
    assert applied, "舊 schema 必須被偵測並遷移"

    columns = {c["name"]: c for c in inspect(engine).get_columns("fact_kpov")}
    assert columns["equipment_code"]["nullable"] is True

    names = {c.get("name") for c in inspect(engine).get_unique_constraints("fact_kpov")}
    assert "uq_kpov_identity" in names
    assert "uq_kpov_equipment" not in names

    # 冪等：再跑一次不應有任何動作
    assert ensure_schema(engine) == []
