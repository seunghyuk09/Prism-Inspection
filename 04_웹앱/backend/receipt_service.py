# -*- coding: utf-8 -*-
"""입고(receipt) · 로트(lot) 서비스.

흐름: 공급사별 입고 등록 → 입고 1건을 여러 로트로 분리.
규칙(rules.py):
  - can_create_new_receipt: 활성(ACTIVE) 공급사만 신규 입고(오프렌 등 REMNANT 금지)
  - lots_within_receipt: Σ로트수량 ≤ 입고수량
"""
from __future__ import annotations

import db
import rules


# ── 조회 ─────────────────────────────────────────────────────
def list_all() -> list[dict]:
    """입고 목록 + 공급사/프리즘명 + 로트수·분리합계."""
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT r.id, r.receipt_no, r.receipt_date, r.received_qty, r.supplier_lot_no, r.note, "
            "       s.name AS supplier_name, s.status AS supplier_status, "
            "       pm.prism_type AS prism_type, pm.spec AS prism_spec, "
            "       (SELECT COUNT(*) FROM lot l WHERE l.receipt_id=r.id) AS lot_count, "
            "       (SELECT COALESCE(SUM(l.lot_qty),0) FROM lot l WHERE l.receipt_id=r.id) AS lot_qty_sum "
            "FROM receipt r "
            "JOIN supplier s ON s.id=r.supplier_id "
            "JOIN prism_master pm ON pm.id=r.prism_id "
            "ORDER BY r.receipt_date DESC, r.id DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["remaining_qty"] = d["received_qty"] - d["lot_qty_sum"]   # 미분리 잔여
            out.append(d)
        return out
    finally:
        conn.close()


def detail(receipt_id) -> dict:
    """입고 1건 상세 + 로트 목록."""
    conn = db.connect()
    try:
        r = conn.execute(
            "SELECT r.*, s.name AS supplier_name, s.status AS supplier_status, "
            "       pm.prism_type AS prism_type, pm.spec AS prism_spec "
            "FROM receipt r JOIN supplier s ON s.id=r.supplier_id "
            "JOIN prism_master pm ON pm.id=r.prism_id WHERE r.id=?", (receipt_id,)).fetchone()
        if not r:
            return {"ok": False, "error": "입고를 찾을 수 없습니다."}
        lots = [dict(x) for x in conn.execute(
            "SELECT id,lot_no,lot_qty,split_reason,status FROM lot WHERE receipt_id=? ORDER BY id",
            (receipt_id,)).fetchall()]
        lot_sum = sum(l["lot_qty"] for l in lots)
        rec = dict(r)
        return {"ok": True, "receipt": rec, "lots": lots,
                "lot_qty_sum": lot_sum, "remaining_qty": rec["received_qty"] - lot_sum}
    finally:
        conn.close()


# ── 채번 ─────────────────────────────────────────────────────
def _auto_receipt_no(conn, receipt_date: str) -> str:
    """입고번호 자동 생성: RCV-YYYYMMDD-### (해당 일자 순번)."""
    ymd = (receipt_date or db.now_str()[:10]).replace("-", "")
    n = conn.execute("SELECT COUNT(*) AS c FROM receipt WHERE REPLACE(receipt_date,'-','')=?",
                     (ymd,)).fetchone()["c"] + 1
    return f"RCV-{ymd}-{n:03d}"


def _auto_lot_no(conn, receipt_id, receipt_no: str) -> str:
    """로트번호 자동 생성: {입고번호}-L## (해당 입고 순번)."""
    n = conn.execute("SELECT COUNT(*) AS c FROM lot WHERE receipt_id=?", (receipt_id,)).fetchone()["c"] + 1
    return f"{receipt_no}-L{n:02d}"


# ── 입고 등록 ────────────────────────────────────────────────
def create(data: dict) -> dict:
    receipt_date = (data.get("receipt_date") or "").strip()
    prism_id = data.get("prism_id")
    supplier_id = data.get("supplier_id")
    received_qty = rules._to_int(data.get("received_qty"))
    receipt_no = (data.get("receipt_no") or "").strip()
    supplier_lot_no = (data.get("supplier_lot_no") or "").strip()
    operator = (data.get("operator") or "").strip()
    note = (data.get("note") or "").strip()

    # 기본 검증
    if not receipt_date:
        return {"ok": False, "error": "입고일자를 입력하세요."}
    if not prism_id:
        return {"ok": False, "error": "프리즘을 선택하세요."}
    if received_qty <= 0:
        return {"ok": False, "error": "입고수량은 1 이상이어야 합니다."}

    conn = db.connect()
    try:
        prism = conn.execute(
            "SELECT id, supplier_id, paint_state FROM prism_master WHERE id=?", (prism_id,)).fetchone()
        if not prism:
            return {"ok": False, "error": "프리즘을 찾을 수 없습니다."}
        # 규칙: 도장완료(PAINTED) 코드는 페인트 결과물 → 직접 입고 불가
        if not rules.is_receivable_prism(prism["paint_state"]):
            return {"ok": False, "error": "도장완료 코드는 직접 입고할 수 없습니다(페인트후검사로 생성됨)."}
        # 공급사: 명시값 없으면 프리즘의 공급사로 자동 결정(코드가 공급사를 품음)
        if not supplier_id:
            supplier_id = prism["supplier_id"]
        if not supplier_id:
            return {"ok": False, "error": "이 프리즘에 공급사가 지정돼 있지 않습니다. 프리즘마스터에서 공급사를 먼저 지정하세요."}
        sup = conn.execute("SELECT status FROM supplier WHERE id=?", (supplier_id,)).fetchone()
        if not sup:
            return {"ok": False, "error": "공급사를 찾을 수 없습니다."}
        # 규칙: 신규 입고는 활성 공급사만(오프렌=REMNANT 는 잔량 소진만)
        if not rules.can_create_new_receipt(sup["status"]):
            return {"ok": False, "error": "활성(ACTIVE) 공급사만 신규 입고가 가능합니다. (잔량관리/중단 공급사는 불가)"}

        ts = db.now_str()
        if not receipt_no:
            receipt_no = _auto_receipt_no(conn, receipt_date)
        cur = conn.execute(
            "INSERT INTO receipt(receipt_no,receipt_date,prism_id,supplier_id,received_qty,"
            "supplier_lot_no,operator,note,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (receipt_no, receipt_date, prism_id, supplier_id, received_qty,
             supplier_lot_no, operator, note, ts, ts))
        receipt_id = cur.lastrowid
        conn.commit()
        return {"ok": True, "receipt_id": receipt_id, "receipt_no": receipt_no}
    except db.sqlite3.IntegrityError:
        return {"ok": False, "error": f"이미 있는 입고번호입니다: {receipt_no}"}
    finally:
        conn.close()


# ── 로트 추가(분리) ──────────────────────────────────────────
def add_lot(data: dict) -> dict:
    receipt_id = data.get("receipt_id")
    lot_qty = rules._to_int(data.get("lot_qty"))
    lot_no = (data.get("lot_no") or "").strip()
    split_reason = (data.get("split_reason") or "").strip()

    if lot_qty <= 0:
        return {"ok": False, "error": "로트수량은 1 이상이어야 합니다."}

    conn = db.connect()
    try:
        rec = conn.execute("SELECT id,receipt_no,received_qty FROM receipt WHERE id=?",
                           (receipt_id,)).fetchone()
        if not rec:
            return {"ok": False, "error": "입고를 찾을 수 없습니다."}
        cur_sum = conn.execute("SELECT COALESCE(SUM(lot_qty),0) AS s FROM lot WHERE receipt_id=?",
                               (receipt_id,)).fetchone()["s"]
        # 규칙: Σ로트수량 ≤ 입고수량
        if not rules.lots_within_receipt(cur_sum + lot_qty, rec["received_qty"]):
            remain = rec["received_qty"] - cur_sum
            return {"ok": False, "error": f"로트 합계가 입고수량을 초과합니다. (잔여 {remain} 까지 가능)"}

        ts = db.now_str()
        if not lot_no:
            lot_no = _auto_lot_no(conn, receipt_id, rec["receipt_no"])
        conn.execute(
            "INSERT INTO lot(receipt_id,lot_no,lot_qty,split_reason,status,created_at,updated_at) "
            "VALUES (?,?,?,?, 'CREATED', ?,?)", (receipt_id, lot_no, lot_qty, split_reason, ts, ts))
        conn.commit()
        return {"ok": True, "lot_no": lot_no}
    except db.sqlite3.IntegrityError:
        return {"ok": False, "error": f"이미 있는 로트번호입니다: {lot_no}"}
    finally:
        conn.close()


def delete_lot(data: dict) -> dict:
    """로트 삭제(검사 시작 전 분리 수정용). 검사가 붙은 로트는 막는다."""
    lot_id = data.get("id")
    conn = db.connect()
    try:
        used = conn.execute("SELECT 1 FROM inspection WHERE lot_id=?", (lot_id,)).fetchone()
        if used:
            return {"ok": False, "error": "이미 검사가 등록된 로트는 삭제할 수 없습니다."}
        cur = conn.execute("DELETE FROM lot WHERE id=?", (lot_id,))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "로트를 찾을 수 없습니다."}
        return {"ok": True}
    finally:
        conn.close()
