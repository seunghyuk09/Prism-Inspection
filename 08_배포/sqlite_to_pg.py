# -*- coding: utf-8 -*-
"""SQLite(prism.sqlite) → PostgreSQL 데이터 덤프 생성기.

schema_postgres.sql 로 스키마(prism)를 먼저 만든 뒤, 이 스크립트로 생성한
prism_data.sql 을 적재한다. psycopg 등 드라이버 불필요(표준 sqlite3 만 사용).

  python 08_배포/sqlite_to_pg.py
  psql "<conn>" -f 08_배포/schema_postgres.sql
  psql "<conn>" -f 08_배포/prism_data.sql

주의: prism_data.sql 은 실데이터라 .gitignore 로 제외됨(GitHub 업로드 금지).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQLITE = ROOT / "02_DB" / "prism.sqlite"
OUT = Path(__file__).resolve().parent / "prism_data.sql"

# FK 의존성 순서(부모 → 자식)
ORDER = ["supplier", "inspection_item", "prism_master", "product", "receipt", "lot",
         "inspection", "inspection_defect", "paint_job", "paint_return",
         "production_plan", "production_plan_line", "consumption",
         "stock_adjustment", "activity_log"]

# 생성열(INSERT 대상 제외) — supplier.is_active 는 status 파생 저장열
GENERATED = {"supplier": {"is_active"}}


def lit(v):
    """PostgreSQL SQL 리터럴로 변환."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def main():
    con = sqlite3.connect(str(SQLITE))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    out = [
        "-- Prism 데이터 (SQLite -> PostgreSQL). schema_postgres.sql 를 먼저 실행하세요.",
        "SET search_path TO prism, public;",
        "BEGIN;",
    ]

    for t in ORDER:
        cols = [r["name"] for r in cur.execute(f"PRAGMA table_info({t})")]
        skip = GENERATED.get(t, set())
        usecols = [c for c in cols if c not in skip]
        rows = cur.execute(f"SELECT * FROM {t}").fetchall()
        out.append(f"-- {t}: {len(rows)} rows")
        for r in rows:
            if t == "prism_master":
                # 자기참조 FK(painted_into_id) 는 NULL 로 넣고 나중에 UPDATE 로 복원
                vals = [(lit(r[c]) if c != "painted_into_id" else "NULL") for c in usecols]
            else:
                vals = [lit(r[c]) for c in usecols]
            out.append(f"INSERT INTO {t} ({', '.join(usecols)}) VALUES ({', '.join(vals)});")

    # prism_master 페어링(자기참조) 복원
    out.append("-- prism_master 페어링(RAW -> PAINTED) 복원")
    for r in cur.execute("SELECT id, painted_into_id FROM prism_master WHERE painted_into_id IS NOT NULL"):
        out.append(f"UPDATE prism_master SET painted_into_id={r['painted_into_id']} WHERE id={r['id']};")

    # IDENTITY 시퀀스 재설정(빈 테이블은 next=1, 있으면 next=max+1)
    out.append("-- IDENTITY 시퀀스 재설정")
    for t in ORDER:
        cols = [r["name"] for r in cur.execute(f"PRAGMA table_info({t})")]
        if "id" in cols:
            out.append(
                f"SELECT setval(pg_get_serial_sequence('prism.{t}','id'), "
                f"COALESCE(MAX(id),1), MAX(id) IS NOT NULL) FROM {t};")

    out.append("COMMIT;")

    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    con.close()
    print(f"[OK] {OUT}  ({len(out)} lines)")


if __name__ == "__main__":
    main()
