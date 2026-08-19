# -*- coding: utf-8 -*-
"""페인트 외주(paint_job) · 분할 회수(paint_return) 서비스.

흐름: 입고검사 양품 → 외주 발송 → (여러 번) 회수.
규칙(rules.py):
  - can_create_paint_job: 플라스틱 + 입고검사 완료
  - paint_send_valid: 발송 ≤ (입고검사 양품 − 이미 발송)
  - paint_return_valid: Σ회수 ≤ 발송
  - is_returned = (Σ회수 == 발송)
"""
from __future__ import annotations

import db
import rules


def _incoming_good(conn, lot_id):
    row = conn.execute("SELECT good_qty,is_complete FROM inspection WHERE lot_id=? AND stage='INCOMING'",
                       (lot_id,)).fetchone()
    if not row:
        return None, False
    return row["good_qty"], bool(row["is_complete"])


def _sent_sum(conn, lot_id):
    return conn.execute("SELECT COALESCE(SUM(sent_qty),0) AS s FROM paint_job WHERE lot_id=?",
                        (lot_id,)).fetchone()["s"]


def create_job(data: dict) -> dict:
    lot_id = data.get("lot_id")
    vendor = (data.get("vendor") or "").strip()
    sent_date = (data.get("sent_date") or "").strip()
    sent_qty = rules._to_int(data.get("sent_qty"))
    if not sent_date:
        return {"ok": False, "error": "발송일을 입력하세요."}
    if sent_qty <= 0:
        return {"ok": False, "error": "발송수량은 1 이상이어야 합니다."}

    conn = db.connect()
    try:
        lot = conn.execute(
            "SELECT l.id, pm.prism_type FROM lot l JOIN receipt r ON r.id=l.receipt_id "
            "JOIN prism_master pm ON pm.id=r.prism_id WHERE l.id=?", (lot_id,)).fetchone()
        if not lot:
            return {"ok": False, "error": "로트를 찾을 수 없습니다."}
        good, complete = _incoming_good(conn, lot_id)
        # 규칙: 플라스틱 + 입고검사 완료라야 발송 가능
        if not rules.can_create_paint_job(lot["prism_type"], complete):
            return {"ok": False, "error": "입고검사 완료된 플라스틱 로트만 페인트 발송이 가능합니다."}
        sent_so_far = _sent_sum(conn, lot_id)
        remaining_good = good - sent_so_far
        # 규칙: 발송 ≤ (양품 − 이미 발송)
        if not rules.paint_send_valid(sent_qty, remaining_good):
            return {"ok": False, "error": f"발송수량이 발송 가능 잔량({remaining_good})을 초과합니다."}

        ts = db.now_str()
        conn.execute(
            "INSERT INTO paint_job(lot_id,vendor,sent_date,sent_qty,is_returned,note,created_at,updated_at) "
            "VALUES (?,?,?,?,0,?,?,?)", (lot_id, vendor, sent_date, sent_qty, (data.get("note") or "").strip(), ts, ts))
        conn.execute("UPDATE lot SET status='PAINTING',updated_at=? WHERE id=? AND status IN ('CREATED','INCOMING_DONE')",
                     (ts, lot_id))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def add_return(data: dict) -> dict:
    job_id = data.get("paint_job_id")
    returned_date = (data.get("returned_date") or "").strip()
    returned_qty = rules._to_int(data.get("returned_qty"))
    if not returned_date:
        return {"ok": False, "error": "회수일을 입력하세요."}
    if returned_qty <= 0:
        return {"ok": False, "error": "회수수량은 1 이상이어야 합니다."}

    conn = db.connect()
    try:
        job = conn.execute("SELECT id,sent_qty FROM paint_job WHERE id=?", (job_id,)).fetchone()
        if not job:
            return {"ok": False, "error": "페인트 발송 건을 찾을 수 없습니다."}
        ret_so_far = conn.execute("SELECT COALESCE(SUM(returned_qty),0) AS s FROM paint_return WHERE paint_job_id=?",
                                  (job_id,)).fetchone()["s"]
        # 규칙: Σ회수 ≤ 발송
        if not rules.paint_return_valid(ret_so_far + returned_qty, job["sent_qty"]):
            remain = job["sent_qty"] - ret_so_far
            return {"ok": False, "error": f"회수수량이 미회수 잔량({remain})을 초과합니다."}

        ts = db.now_str()
        conn.execute("INSERT INTO paint_return(paint_job_id,returned_date,returned_qty,note,created_at) VALUES (?,?,?,?,?)",
                     (job_id, returned_date, returned_qty, (data.get("note") or "").strip(), ts))
        # is_returned 파생 갱신
        new_sum = ret_so_far + returned_qty
        conn.execute("UPDATE paint_job SET is_returned=?,updated_at=? WHERE id=?",
                     (1 if rules.paint_fully_returned(new_sum, job["sent_qty"]) else 0, ts, job_id))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def delete_job(data: dict) -> dict:
    """발송 건 삭제(회수가 없을 때만). 페인트후검사가 시작됐으면 차단."""
    job_id = data.get("id")
    conn = db.connect()
    try:
        if conn.execute("SELECT 1 FROM paint_return WHERE paint_job_id=?", (job_id,)).fetchone():
            return {"ok": False, "error": "회수 기록이 있는 발송 건은 삭제할 수 없습니다."}
        cur = conn.execute("DELETE FROM paint_job WHERE id=?", (job_id,))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "발송 건을 찾을 수 없습니다."}
        return {"ok": True}
    finally:
        conn.close()
