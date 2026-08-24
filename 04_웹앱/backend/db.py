# -*- coding: utf-8 -*-
"""SQLite 연결 · 스키마 생성 · 초기 시드.

설계 방침:
  - 외부 의존성 없음(파이썬 표준 sqlite3만 사용).
  - 규칙/상태는 가급적 boolean(0/1) 컬럼으로 — is_active, is_complete, is_returned 등.
  - 검사항목은 롱포맷(inspection_defect)으로 — 항목이 늘어도 컬럼 변경 불필요.
  - 미완료(점진 기록) 허용: 수량 등식은 코드에서 is_complete 로 게이팅(완료=hard, 미완료=soft).
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path


# ── 경로 ─────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]   # 프로젝트 루트
DB_DIR = ROOT / "02_DB"
DB_PATH = DB_DIR / "prism.sqlite"

# ── 백엔드 선택: DATABASE_URL 있으면 PostgreSQL, 없으면 SQLite(기본) ──
# 서비스 코드는 그대로 두고, 연결 래퍼가 방언 차이(?→%s, INSERT OR IGNORE,
# lastrowid, IntegrityError)를 흡수한다.
# 접속정보 우선순위: 환경변수 > 00_설정/db.env(KEY=VALUE, git 제외) > 기본(SQLite).
def _load_db_env() -> dict:
    cfg = {}
    f = ROOT / "00_설정" / "db.env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


_DBENV = _load_db_env()
DATABASE_URL = (os.environ.get("DATABASE_URL") or _DBENV.get("DATABASE_URL") or "").strip()
# DATABASE_URL 이 채워져 있으면 PG 모드. URL 형식(postgresql://...) 과
# 키=값 형식(host=... user=... password=...) 둘 다 허용(특수문자 비번 안전).
IS_PG = bool(DATABASE_URL)
PG_SCHEMA = (os.environ.get("PG_SCHEMA") or _DBENV.get("PG_SCHEMA") or "prism").strip() or "prism"
SCHEMA_PG_FILE = ROOT / "08_배포" / "schema_postgres.sql"


def now_str() -> str:
    """현재시각 문자열(기록용)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 스키마 (데이터 모델 v2.2) ────────────────────────────────
# 새 테이블/컬럼을 추가할 때는 아래 SQL에 한 줄씩 더한다(IF NOT EXISTS 라 재실행 안전).
SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;

-- 프리즘 마스터: 관리 대상 프리즘(종류/규격/도장상태). item_code 는 ERP 품목코드.
-- 플라스틱은 미도장(RAW)→페인트→도장완료(PAINTED) 로 코드가 페어를 이룬다.
CREATE TABLE IF NOT EXISTS prism_master (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_code       TEXT,                                   -- ERP 품목코드
    prism_type      TEXT NOT NULL CHECK (prism_type IN ('PLASTIC','GLASS')),
    model           TEXT,                                   -- U20 / U10 / U30 등
    spec            TEXT,                                   -- 품목명/규격
    supplier_id     INTEGER,                                -- 이 코드의 공급사(코드가 공급사를 품음)
    paint_state     TEXT NOT NULL DEFAULT 'NONE'            -- RAW(미도장)/PAINTED(도장완료)/NONE(유리 등)
                    CHECK (paint_state IN ('RAW','PAINTED','NONE')),
    painted_into_id INTEGER,                                -- RAW → 도장완료 코드(페어) FK
    unit            TEXT NOT NULL DEFAULT 'EA',
    is_active       INTEGER NOT NULL DEFAULT 1,             -- 사용여부(boolean)
    note            TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (supplier_id)     REFERENCES supplier(id),
    FOREIGN KEY (painted_into_id) REFERENCES prism_master(id)
);
-- 품목코드는 입력된 경우에만 유일(부분 유니크).
CREATE UNIQUE INDEX IF NOT EXISTS ux_prism_item_code
    ON prism_master(item_code) WHERE item_code IS NOT NULL;

-- 공급사: 오프렌=REMNANT(폐업·잔량관리), ALT=ACTIVE.
-- is_active 는 status 에서 파생(생성 컬럼) → 중복/모순 방지.
CREATE TABLE IF NOT EXISTS supplier (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    status       TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','REMNANT','STOPPED')),
    is_active    INTEGER GENERATED ALWAYS AS (CASE WHEN status='ACTIVE' THEN 1 ELSE 0 END) VIRTUAL,
    note         TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- 검사항목 마스터(확장형). 단계별 적용을 boolean 으로.
CREATE TABLE IF NOT EXISTS inspection_item (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    name                   TEXT NOT NULL UNIQUE,
    category               TEXT,
    applies_to_incoming    INTEGER NOT NULL DEFAULT 1,   -- 입고검사 적용(boolean)
    applies_to_post_paint  INTEGER NOT NULL DEFAULT 1,   -- 페인트후검사 적용(boolean)
    sort_order             INTEGER NOT NULL DEFAULT 0,
    is_active              INTEGER NOT NULL DEFAULT 1,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

-- 제품마스터(BOM): 완제품 → 어떤 프리즘 + 대당 소요량. prism_id NULL = 프리즘 미사용 제품.
CREATE TABLE IF NOT EXISTS product (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code    TEXT NOT NULL UNIQUE,               -- 구매계획서 PRODUCT 문자열
    product_name    TEXT,
    prism_id        INTEGER,                            -- FK prism_master (NULL=미사용)
    prism_per_unit  INTEGER NOT NULL DEFAULT 1,         -- 대당 프리즘 소요량
    is_active       INTEGER NOT NULL DEFAULT 1,
    note            TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (prism_id) REFERENCES prism_master(id)
);

-- 입고(헤더): 공급사별 입고 수량·일자.
CREATE TABLE IF NOT EXISTS receipt (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no       TEXT NOT NULL UNIQUE,
    receipt_date     TEXT NOT NULL,
    prism_id         INTEGER NOT NULL,
    supplier_id      INTEGER NOT NULL,
    received_qty     INTEGER NOT NULL CHECK (received_qty > 0),
    supplier_lot_no  TEXT,
    operator         TEXT,
    note             TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    FOREIGN KEY (prism_id)    REFERENCES prism_master(id),
    FOREIGN KEY (supplier_id) REFERENCES supplier(id)
);

-- 로트: 입고 1건 → 여러 로트. 검사·집계의 기본 단위.
CREATE TABLE IF NOT EXISTS lot (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id    INTEGER NOT NULL,
    lot_no        TEXT NOT NULL,
    lot_qty       INTEGER NOT NULL CHECK (lot_qty > 0),
    split_reason  TEXT,
    status        TEXT NOT NULL DEFAULT 'CREATED'
                  CHECK (status IN ('CREATED','INCOMING_DONE','PAINTING','POST_PAINT_DONE','CLOSED')),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (receipt_id, lot_no),
    FOREIGN KEY (receipt_id) REFERENCES receipt(id)
);

-- 검사: 로트당 단계별(입고검사/페인트후검사). 미완료(is_complete=0) 허용.
CREATE TABLE IF NOT EXISTS inspection (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id         INTEGER NOT NULL,
    stage          TEXT NOT NULL CHECK (stage IN ('INCOMING','POST_PAINT')),
    method         TEXT NOT NULL DEFAULT 'FULL' CHECK (method IN ('FULL','SAMPLING')),
    start_date     TEXT,
    end_date       TEXT,
    inspected_qty  INTEGER NOT NULL DEFAULT 0,
    good_qty       INTEGER NOT NULL DEFAULT 0,
    defect_qty     INTEGER NOT NULL DEFAULT 0,
    sample_size    INTEGER,                              -- AQL 전환 대비
    accept_count   INTEGER,                              -- AQL Ac
    reject_count   INTEGER,                              -- AQL Re
    aql_level      TEXT,
    judgment       TEXT CHECK (judgment IN ('PASS','FAIL','CONDITIONAL')),
    inspector      TEXT,
    is_complete    INTEGER NOT NULL DEFAULT 0,           -- 완료여부(boolean) — 점진 기록 게이팅
    note           TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE (lot_id, stage),
    FOREIGN KEY (lot_id) REFERENCES lot(id)
);

-- 검사불량(롱포맷): 검사 × 검사항목 별 불량수량.
CREATE TABLE IF NOT EXISTS inspection_defect (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id       INTEGER NOT NULL,
    inspection_item_id  INTEGER NOT NULL,
    defect_qty          INTEGER NOT NULL DEFAULT 0,
    UNIQUE (inspection_id, inspection_item_id),
    FOREIGN KEY (inspection_id)      REFERENCES inspection(id),
    FOREIGN KEY (inspection_item_id) REFERENCES inspection_item(id)
);

-- 페인트 외주(발송). 회수는 분할 가능 → paint_return 으로 분리.
CREATE TABLE IF NOT EXISTS paint_job (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id       INTEGER NOT NULL,
    vendor       TEXT,
    sent_date    TEXT NOT NULL,
    sent_qty     INTEGER NOT NULL CHECK (sent_qty > 0),
    is_returned  INTEGER NOT NULL DEFAULT 0,             -- Σ회수==발송 일 때 1
    note         TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY (lot_id) REFERENCES lot(id)
);

-- 페인트 분할 회수.
CREATE TABLE IF NOT EXISTS paint_return (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    paint_job_id   INTEGER NOT NULL,
    returned_date  TEXT NOT NULL,
    returned_qty   INTEGER NOT NULL CHECK (returned_qty > 0),
    note           TEXT,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (paint_job_id) REFERENCES paint_job(id)
);

-- 구매/생산계획(임포트 헤더). is_final = 월말 최종본 여부.
CREATE TABLE IF NOT EXISTS production_plan (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_month   TEXT NOT NULL,                          -- 예: '2026-06'
    source_file  TEXT,
    is_final     INTEGER NOT NULL DEFAULT 0,
    imported_at  TEXT,
    note         TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- 구매계획 상세(제품별 생산수량 → 프리즘 소비량).
CREATE TABLE IF NOT EXISTS production_plan_line (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id       INTEGER NOT NULL,
    product_code  TEXT NOT NULL,                         -- 시트 원본 PRODUCT
    planned_qty   INTEGER NOT NULL DEFAULT 0,            -- 시트 Q'ty
    product_id    INTEGER,                               -- 매칭된 제품마스터(FK)
    prism_id      INTEGER,                               -- 해소된 프리즘
    consumed_qty  INTEGER NOT NULL DEFAULT 0,            -- planned_qty * prism_per_unit
    note          TEXT,
    FOREIGN KEY (plan_id)    REFERENCES production_plan(id),
    FOREIGN KEY (product_id) REFERENCES product(id),
    FOREIGN KEY (prism_id)   REFERENCES prism_master(id)
);

-- 소비 원장: 프리즘 재고를 줄이는 모든 차감 기록(잔량 계산의 음수측).
CREATE TABLE IF NOT EXISTS consumption (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prism_id        INTEGER NOT NULL,
    supplier_id     INTEGER,                             -- 차감 귀속 공급사(NULL=풀)
    source          TEXT NOT NULL CHECK (source IN ('PLAN','MANUAL','ADJUST')),
    source_plan_id  INTEGER,
    qty             INTEGER NOT NULL,
    consumed_at     TEXT NOT NULL,
    note            TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (prism_id)       REFERENCES prism_master(id),
    FOREIGN KEY (supplier_id)    REFERENCES supplier(id),
    FOREIGN KEY (source_plan_id) REFERENCES production_plan(id)
);

-- 재고 보정: 기초재고(OPENING, 오프렌 잔량 등)·수기 보정(MANUAL). 부호 있는 수량.
CREATE TABLE IF NOT EXISTS stock_adjustment (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    prism_id     INTEGER NOT NULL,
    qty          INTEGER NOT NULL,                       -- +기초재고/보정, -감모
    reason       TEXT NOT NULL DEFAULT 'OPENING' CHECK (reason IN ('OPENING','MANUAL')),
    adjusted_at  TEXT NOT NULL,
    note         TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (prism_id) REFERENCES prism_master(id)
);

-- 사용불가(불량/보류) 재고: 현재고에는 포함되나 실제 사용 불가한 수량(표시용).
-- +추가 / -해소(반납·폐기 시). on_hand 계산에는 영향 없음(가용 = 현재고 - 사용불가).
CREATE TABLE IF NOT EXISTS unusable_stock (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    prism_id     INTEGER NOT NULL,
    qty          INTEGER NOT NULL,
    category     TEXT NOT NULL DEFAULT '불량',
    dated        TEXT NOT NULL,
    note         TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (prism_id) REFERENCES prism_master(id)
);

-- 행위/이력 로그: 로그인은 없지만 '누가(operator) 언제 무엇을' 기록(기록 신뢰성).
CREATE TABLE IF NOT EXISTS activity_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    category   TEXT,
    action     TEXT,
    target     TEXT,
    detail     TEXT,                                     -- JSON 문자열
    operator   TEXT
);
"""


# ── PostgreSQL 호환 래퍼 (서비스 코드 무변경) ────────────────
def _translate(sql: str) -> str:
    """SQLite SQL → PostgreSQL SQL. ?→%s, INSERT OR IGNORE→ON CONFLICT DO NOTHING."""
    on_conflict = bool(re.match(r"(?is)\s*INSERT\s+OR\s+IGNORE\s+INTO\b", sql))
    if on_conflict:
        sql = re.sub(r"(?is)^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, count=1)
    sql = sql.replace("?", "%s")
    if on_conflict:
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return sql


def _split_sql(script: str) -> list:
    """스키마 스크립트를 개별 문장으로 분리(문자열 내 세미콜론 없음 가정 — 본 스키마 안전)."""
    no_comments = "\n".join(line.split("--", 1)[0] for line in script.splitlines())
    return [s.strip() for s in no_comments.split(";") if s.strip()]


class _PgCursor:
    """psycopg 커서를 sqlite3 커서처럼(iter/fetch/lastrowid)."""
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur.fetchall())


class _PgConn:
    """psycopg 연결을 sqlite3.Connection 처럼 보이게 하는 얇은 래퍼."""
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        import psycopg
        q = _translate(sql)
        # INSERT 는 lastrowid 대체용 RETURNING id 자동 부가(모든 테이블에 id 존재)
        want_id = q.lstrip()[:6].upper() == "INSERT" and " RETURNING " not in q.upper()
        if want_id:
            q = q.rstrip().rstrip(";") + " RETURNING id"
        cur = self._raw.cursor()
        try:
            cur.execute(q, tuple(params) if params else None)
        except psycopg.errors.IntegrityError as e:
            # 서비스는 db.sqlite3.IntegrityError 로 잡으므로 타입 통일
            raise sqlite3.IntegrityError(str(e))
        wrap = _PgCursor(cur)
        if want_id:
            try:
                row = cur.fetchone()
                if row is not None:
                    wrap.lastrowid = row["id"] if isinstance(row, dict) else row[0]
            except Exception:  # noqa: BLE001 (ON CONFLICT 로 미삽입 시 RETURNING 0행)
                wrap.lastrowid = None
        return wrap

    def executescript(self, script):
        cur = self._raw.cursor()
        for stmt in _split_sql(script):
            cur.execute(stmt)
        return _PgCursor(cur)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


# ── 연결 ─────────────────────────────────────────────────────
def connect():
    """행을 dict 처럼 다루는 연결을 반환 (SQLite 기본 / PostgreSQL 은 래퍼)."""
    if IS_PG:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as e:
            raise RuntimeError("PostgreSQL 사용 시 psycopg 필요: pip install \"psycopg[binary]\"") from e
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row,
                              options=f"-c search_path={PG_SCHEMA},public")
        return _PgConn(raw)
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_columns(conn, table, columns):
    """기존 DB 에 누락된 컬럼을 ALTER 로 추가(있으면 건너뜀)."""
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns:
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _migrate(conn) -> None:
    """스키마 변경 마이그레이션(기존 prism_master 에 도장상태/페어/공급사 컬럼 추가)."""
    _ensure_columns(conn, "prism_master", [
        ("model", "model TEXT"),
        ("supplier_id", "supplier_id INTEGER"),
        ("paint_state", "paint_state TEXT NOT NULL DEFAULT 'NONE'"),
        ("painted_into_id", "painted_into_id INTEGER"),
    ])


def init_db() -> None:
    """스키마 생성 + 마이그레이션 + 초기 시드(여러 번 호출해도 안전)."""
    if IS_PG:
        _init_pg()
        return
    conn = connect()
    try:
        conn.executescript(SCHEMA_SQL)
        _migrate(conn)
        conn.commit()
        _seed(conn)
    finally:
        conn.close()


def _init_pg() -> None:
    """PostgreSQL: prism 스키마가 없으면 DDL 로드 + 시드. 이미 있으면(이관 완료) 유지.
    부팅 직후 PG 서비스가 아직 안 떴을 수 있어 초기 접속을 잠깐 재시도한다(창 없는 자동시작 대비)."""
    import time
    conn = None
    for attempt in range(15):
        try:
            conn = connect()
            break
        except Exception:  # noqa: BLE001 — PG 미기동 시 재시도
            if attempt >= 14:
                raise
            time.sleep(2)
    try:
        r = conn.execute("SELECT to_regclass(?) AS r", (f"{PG_SCHEMA}.supplier",)).fetchone()
        exists = r is not None and r["r"] is not None
        if not exists:
            if SCHEMA_PG_FILE.exists():
                conn.executescript(SCHEMA_PG_FILE.read_text(encoding="utf-8"))
                conn.commit()
            _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    """기본 데이터 시드 — 이미 있으면 무시(INSERT OR IGNORE)."""
    ts = now_str()

    # 공급사 4곳: ALT(활성)·오프렌(잔량관리)·TianCheng·WooKyung
    suppliers = [("ALT", "ACTIVE", "현행 플라스틱 대체 공급사"),
                 ("오프렌", "REMNANT", "폐업 — 잔량 소진 관리"),
                 ("TianCheng", "ACTIVE", "유리/U30 공급사"),
                 ("WooKyung", "ACTIVE", "유리(U10) 공급사")]
    for name, status, note in suppliers:
        conn.execute(
            "INSERT OR IGNORE INTO supplier(name,status,note,created_at,updated_at) "
            "VALUES (?,?,?,?,?)", (name, status, note, ts, ts))
    sup = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM supplier")}

    # 과거 placeholder 프리즘 제거(참조 없을 때만 — 실제 코드로 대체)
    conn.execute("DELETE FROM prism_master WHERE item_code IS NULL "
                 "AND spec IN ('Plastic Prism (기본)','Glass Prism (기본)')")

    # 프리즘 8종(ERP 실제 코드). item_code 기준 idempotent.
    # (item_code, type, model, 품목명, 공급사, 도장상태)
    prisms = [
        ("52791",         "PLASTIC", "U20", "U20 Plastic Prism_ALT [Witnout Paint_ALT]", "ALT",       "RAW"),
        ("SP10-2103-ALT", "PLASTIC", "U20", "U20 Plastic Prism with paint_ALT",          "ALT",       "PAINTED"),
        ("A0001",         "PLASTIC", "U20", "U20 Plastic Prism [오프렌]",                  "오프렌",     "RAW"),
        ("SP10-2103",     "PLASTIC", "U20", "U20 Plastic Prism with paint",              "오프렌",     "PAINTED"),
        ("SP10-2101",     "GLASS",   "U20", "U20 Glass prism [TianCheng]",               "TianCheng", "NONE"),
        ("SP10-2104",     "GLASS",   "U10", "U10 Glass prism [WooKyung]",                "WooKyung",  "NONE"),
        ("SP10-2105",     "GLASS",   "U10", "U10 Glass prism [TianCheng]",               "TianCheng", "NONE"),
        ("00015",         "GLASS",   "U30", "U30 PRISM",                                  "TianCheng", "NONE"),
    ]
    for code, ptype, model, spec, supname, pstate in prisms:
        if not conn.execute("SELECT 1 FROM prism_master WHERE item_code=?", (code,)).fetchone():
            conn.execute(
                "INSERT INTO prism_master(item_code,prism_type,model,spec,supplier_id,paint_state,unit,is_active,note,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?, 'EA', 1, '', ?, ?)",
                (code, ptype, model, spec, sup.get(supname), pstate, ts, ts))

    # 페어 연결: 미도장(RAW) → 도장완료(PAINTED)
    ids = {r["item_code"]: r["id"] for r in
           conn.execute("SELECT id,item_code FROM prism_master WHERE item_code IS NOT NULL")}
    for raw, painted in [("52791", "SP10-2103-ALT"), ("A0001", "SP10-2103")]:
        if raw in ids and painted in ids:
            conn.execute("UPDATE prism_master SET painted_into_id=?, updated_at=? WHERE id=?",
                         (ids[painted], ts, ids[raw]))

    # 검사항목: 요청한 5종. (단계 적용: 원자재=입고, 페인트/페인트작업불량=페인트후, 디그·스크래치=공통)
    items = [
        # name,                 category, incoming, post, sort
        ("원자재",              "원자재",   1, 0, 1),
        ("디그&찍힘",           "외관",     1, 1, 2),
        ("스크래치",            "외관",     1, 1, 3),
        ("페인트",              "페인트",   0, 1, 4),
        ("페인트 작업 불량",     "도장",     0, 1, 5),
    ]
    for name, cat, inc, post, order in items:
        conn.execute(
            "INSERT OR IGNORE INTO inspection_item"
            "(name,category,applies_to_incoming,applies_to_post_paint,sort_order,is_active,created_at,updated_at) "
            "VALUES (?,?,?,?,?,1,?,?)", (name, cat, inc, post, order, ts, ts))

    conn.commit()


def table_counts(conn: sqlite3.Connection) -> dict:
    """대시보드용: 주요 테이블 행 수."""
    names = ["prism_master", "supplier", "inspection_item", "product",
             "receipt", "lot", "inspection", "paint_job",
             "production_plan", "consumption"]
    out = {}
    for n in names:
        try:
            out[n] = conn.execute(f"SELECT COUNT(*) AS c FROM {n}").fetchone()["c"]
        except Exception:  # noqa: BLE001 (SQLite/PG 공통 — 카운트 실패는 대시보드에 영향만)
            try:
                conn.rollback()   # PG: 오류 후 트랜잭션 복구
            except Exception:  # noqa: BLE001
                pass
            out[n] = None
    return out


if __name__ == "__main__":
    # 단독 실행 시 DB 초기화(스키마+시드)
    init_db()
    c = connect()
    print("DB:", DB_PATH)
    print("counts:", dict(table_counts(c)))
    c.close()
