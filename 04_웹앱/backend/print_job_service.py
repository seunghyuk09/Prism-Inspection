# -*- coding: utf-8 -*-
"""인쇄 작업 서비스 — 미도장(RAW) 프리즘을 With Paint 품목으로 전환한 기록.

인쇄를 하면 품목코드가 바뀌고(예: 52791 → SP10-2103-ALT) 수량도 줄어든다(인쇄 불량).
기록 한 건이 재고 양쪽을 동시에 움직인다:
  - 투입(input_qty)  → RAW 재고에서 차감
  - 산출(output_qty) → With Paint 재고로 증가
재고식은 stock_service 가 print_job 을 합산해서 반영한다.
"""
from __future__ import annotations

import db
import rules


def printable_prisms(data=None) -> dict:
    """인쇄 투입이 가능한 RAW 프리즘 목록(산출 품목이 연결된 것만)."""
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT pm.id, pm.item_code, pm.spec, pm.model, "
            "       pp.id AS painted_id, pp.item_code AS painted_code, pp.spec AS painted_spec "
            "FROM prism_master pm JOIN prism_master pp ON pp.id=pm.painted_into_id "
            "WHERE pm.is_active=1 AND pm.paint_state='RAW' "
            "ORDER BY pm.item_code").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_jobs(data=None) -> dict:
    """인쇄 이력(최근순) + 합계. 수율 = 산출 / 투입."""
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT j.id, j.print_date, j.input_qty, j.output_qty, j.defect_qty, "
            "       j.vendor, j.note, j.operator, j.created_at, "
            "       j.raw_prism_id, j.painted_prism_id, "
            "       rw.item_code AS raw_code, rw.spec AS raw_spec, "
            "       pt.item_code AS painted_code, pt.spec AS painted_spec "
            "FROM print_job j "
            "JOIN prism_master rw ON rw.id=j.raw_prism_id "
            "JOIN prism_master pt ON pt.id=j.painted_prism_id "
            "ORDER BY j.print_date DESC, j.id DESC").fetchall()
        items = []
        for r in rows:
            d = dict(r)
            iq = d["input_qty"] or 0
            d["yield_rate"] = round((d["output_qty"] or 0) / iq * 100, 2) if iq else None
            d["loss_qty"] = iq - (d["output_qty"] or 0) - (d["defect_qty"] or 0)
            items.append(d)
        return items
    finally:
        conn.close()


def _resolve_pair(conn, raw_prism_id):
    """투입 RAW 와 그 산출 With Paint 품목을 찾는다. (row, painted_id, error)"""
    row = conn.execute(
        "SELECT id, item_code, paint_state, painted_into_id FROM prism_master WHERE id=?",
        (raw_prism_id,)).fetchone()
    if not row:
        return None, None, "프리즘을 찾을 수 없습니다."
    if not rules.can_print_prism(row["paint_state"], row["painted_into_id"]):
        return None, None, (f"{row['item_code']} 은(는) 인쇄 투입 대상이 아닙니다. "
                            "기준정보에서 미도장(RAW) + 도장완료 코드 연결을 확인하세요.")
    return row, row["painted_into_id"], None


def save(data: dict) -> dict:
    """인쇄 작업 등록 — {print_date, raw_prism_id, input_qty, output_qty, defect_qty, vendor, note}."""
    raw_prism_id = data.get("raw_prism_id")
    print_date = (data.get("print_date") or "").strip()
    if not raw_prism_id or not print_date:
        return {"ok": False, "error": "인쇄일과 투입 품목을 입력하세요."}

    input_qty = rules._to_int(data.get("input_qty"))
    output_qty = rules._to_int(data.get("output_qty"))
    defect_qty = rules._to_int(data.get("defect_qty"))
    valid, reason = rules.validate_print_job(input_qty, output_qty, defect_qty)
    if not valid:
        return {"ok": False, "error": reason}

    conn = db.connect()
    try:
        _, painted_id, err = _resolve_pair(conn, raw_prism_id)
        if err:
            return {"ok": False, "error": err}
        ts = db.now_str()
        cur = conn.execute(
            "INSERT INTO print_job(print_date,raw_prism_id,painted_prism_id,input_qty,output_qty,"
            "defect_qty,vendor,note,operator,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (print_date, raw_prism_id, painted_id, input_qty, output_qty, defect_qty,
             (data.get("vendor") or "").strip(), (data.get("note") or "").strip(),
             (data.get("operator") or "").strip(), ts, ts))
        conn.commit()
        return {"ok": True, "id": cur.lastrowid, "input_qty": input_qty,
                "output_qty": output_qty, "defect_qty": defect_qty}
    finally:
        conn.close()


def update(data: dict) -> dict:
    """인쇄 작업 수정 — 수량·날짜·비고를 그 자리에서 고친다."""
    jid = data.get("id")
    if not jid:
        return {"ok": False, "error": "작업 ID가 없습니다."}
    input_qty = rules._to_int(data.get("input_qty"))
    output_qty = rules._to_int(data.get("output_qty"))
    defect_qty = rules._to_int(data.get("defect_qty"))
    valid, reason = rules.validate_print_job(input_qty, output_qty, defect_qty)
    if not valid:
        return {"ok": False, "error": reason}

    conn = db.connect()
    try:
        cur_row = conn.execute("SELECT raw_prism_id FROM print_job WHERE id=?", (jid,)).fetchone()
        if not cur_row:
            return {"ok": False, "error": "인쇄 작업을 찾을 수 없습니다."}
        raw_prism_id = data.get("raw_prism_id") or cur_row["raw_prism_id"]
        _, painted_id, err = _resolve_pair(conn, raw_prism_id)
        if err:
            return {"ok": False, "error": err}
        conn.execute(
            "UPDATE print_job SET print_date=?, raw_prism_id=?, painted_prism_id=?, input_qty=?, "
            "output_qty=?, defect_qty=?, vendor=?, note=?, updated_at=? WHERE id=?",
            ((data.get("print_date") or "").strip(), raw_prism_id, painted_id, input_qty,
             output_qty, defect_qty, (data.get("vendor") or "").strip(),
             (data.get("note") or "").strip(), db.now_str(), jid))
        conn.commit()
        return {"ok": True, "input_qty": input_qty, "output_qty": output_qty}
    finally:
        conn.close()


def delete(data: dict) -> dict:
    """인쇄 작업 삭제 — 재고는 자동으로 되돌아간다(합산식이라)."""
    jid = data.get("id")
    conn = db.connect()
    try:
        cur = conn.execute("DELETE FROM print_job WHERE id=?", (jid,))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "인쇄 작업을 찾을 수 없습니다."}
        return {"ok": True}
    finally:
        conn.close()
