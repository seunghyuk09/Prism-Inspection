# -*- coding: utf-8 -*-
"""SQLite → PostgreSQL 실제 이관 실행기.

전제: 00_설정/db.env 에 DATABASE_URL(비밀번호 포함)이 채워져 있어야 함.
동작:
  1) 현재 SQLite(02_DB/prism.sqlite)로 prism_data.sql 최신 생성
  2) PostgreSQL 접속(db.env의 DATABASE_URL)
  3) prism 스키마 없으면 schema_postgres.sql 실행(테이블 생성)
  4) 데이터 적재(이미 있으면 건너뜀 — 중복 방지)
  5) 건수 검증

실행:  python 08_배포/pg_migrate.py   (앱의 64비트 파이썬 사용)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[0] / "04_웹앱" / "backend"
sys.path.insert(0, str(BACKEND))
import db  # noqa: E402  (db.env / DATABASE_URL / _split_sql 재사용)


def _ensure_database(url: str) -> None:
    """대상 데이터베이스가 없으면 'postgres' DB 에 접속해 생성(createdb 권한 필요).
    URL/키=값 두 DSN 형식 모두 지원(psycopg conninfo 파싱)."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    try:
        c = psycopg.connect(url)
        c.close()
        return  # 접속되면 이미 존재
    except psycopg.OperationalError as e:
        if "does not exist" not in str(e).lower():
            raise  # 비번오류 등 다른 문제는 그대로 알림
    info = conninfo_to_dict(url)
    target = info.get("dbname") or "prism"
    admin = make_conninfo(**{**info, "dbname": "postgres"})
    ac = psycopg.connect(admin)
    ac.autocommit = True
    ac.execute(f'CREATE DATABASE "{target}"')
    ac.close()
    print(f"[DB] 데이터베이스 '{target}' 생성됨")


def _run_sql_statements(cur, sql_text):
    """세미콜론 분리 실행. BEGIN/COMMIT 은 psycopg 트랜잭션과 충돌하므로 제외."""
    for stmt in db._split_sql(sql_text):
        u = stmt.strip().upper()
        if u in ("BEGIN", "COMMIT", "START TRANSACTION"):
            continue
        cur.execute(stmt)


def main() -> int:
    if not db.IS_PG:
        print("[중단] DATABASE_URL 이 설정되지 않았습니다.")
        print("       00_설정/db.env 를 만들어 DATABASE_URL 을 채우세요 (db.env.example 참조).")
        return 1

    # 1) 최신 데이터 덤프 생성
    gen = importlib.util.spec_from_file_location("sqlite_to_pg", HERE / "sqlite_to_pg.py")
    mod = importlib.util.module_from_spec(gen)
    gen.loader.exec_module(mod)
    mod.main()  # -> 08_배포/prism_data.sql
    data_sql = (HERE / "prism_data.sql").read_text(encoding="utf-8")

    import psycopg
    from psycopg.rows import dict_row

    _ensure_database(db.DATABASE_URL)   # 대상 DB 없으면 생성
    conn = psycopg.connect(db.DATABASE_URL, row_factory=dict_row)
    conn.autocommit = False
    try:
        cur = conn.cursor()

        # 3) 스키마 존재 여부
        cur.execute("SELECT to_regclass(%s) AS r", (f"{db.PG_SCHEMA}.supplier",))
        schema_exists = cur.fetchone()["r"] is not None
        if not schema_exists:
            print(f"[스키마] '{db.PG_SCHEMA}' 생성 중...")
            _run_sql_statements(cur, db.SCHEMA_PG_FILE.read_text(encoding="utf-8"))
            conn.commit()
            print("[스키마] 생성 완료")
        else:
            print(f"[스키마] '{db.PG_SCHEMA}' 이미 존재")

        # 4) 데이터 적재(중복 방지)
        cur.execute(f"SELECT count(*) AS c FROM {db.PG_SCHEMA}.supplier")
        if cur.fetchone()["c"] > 0:
            print("[데이터] 이미 적재돼 있어 건너뜀. (다시 넣으려면 스키마를 비운 뒤 재실행)")
        else:
            print("[데이터] 적재 중...")
            _run_sql_statements(cur, data_sql)
            conn.commit()
            print("[데이터] 적재 완료")

        # 5) 검증
        print("[검증] 테이블 건수:")
        for t in ("supplier", "prism_master", "inspection_item", "receipt", "lot",
                  "inspection", "inspection_defect", "consumption", "stock_adjustment"):
            cur.execute(f"SELECT count(*) AS c FROM {db.PG_SCHEMA}.{t}")
            print(f"   {t:18s}: {cur.fetchone()['c']}")
        conn.commit()
        print("[완료] PostgreSQL 이관 성공 (OK)")
        return 0
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        print("[실패] 롤백됨:", repr(e))
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
