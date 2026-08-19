# -*- coding: utf-8 -*-
"""입고이력(inbound history) 서비스.

품목(프리즘)별로 입고 날짜를 나열하고, 각 입고건의 검사 상세(양품/불량/불량유형/상태)를 제공한다.
UI(입고이력 패널): 날짜를 '열'로 나열 → 날짜 클릭 시 해당 입고분 상세 표시.

재고 계산식은 stock_service 와 동일(도장상태별). 여기서는 조회 전용.
"""
from __future__ import annotations

import db


def _on_hand(conn, prism_id, paint_state) -> int:
    """도장상태별 현재고(stock_service 와 동일 공식)."""
    adj = conn.execute("SELECT COALESCE(SUM(qty),0) s FROM stock_adjustment WHERE prism_id=?", (prism_id,)).fetchone()["s"]
    consumed = conn.execute("SELECT COALESCE(SUM(qty),0) s FROM consumption WHERE prism_id=?", (prism_id,)).fetchone()["s"]
    ig = conn.execute(
        "SELECT COALESCE(SUM(i.good_qty),0) s FROM inspection i JOIN lot l ON l.id=i.lot_id "
        "JOIN receipt r ON r.id=l.receipt_id WHERE i.stage='INCOMING' AND r.prism_id=?", (prism_id,)).fetchone()["s"]
    sp = conn.execute(
        "SELECT COALESCE(SUM(pj.sent_qty),0) s FROM paint_job pj JOIN lot l ON l.id=pj.lot_id "
        "JOIN receipt r ON r.id=l.receipt_id WHERE r.prism_id=?", (prism_id,)).fetchone()["s"]
    pin = conn.execute(
        "SELECT COALESCE(SUM(i.good_qty),0) s FROM inspection i JOIN lot l ON l.id=i.lot_id "
        "JOIN receipt r ON r.id=l.receipt_id JOIN prism_master pm ON pm.id=r.prism_id "
        "WHERE i.stage='POST_PAINT' AND pm.painted_into_id=?", (prism_id,)).fetchone()["s"]
    if paint_state == "PAINTED":
        return adj + pin - consumed
    if paint_state == "RAW":
        return adj + ig - sp - consumed
    return adj + ig - consumed


def _pct(part, whole):
    return round(part * 100.0 / whole, 2) if whole else None


def inbound_history(data=None) -> dict:
    """입고이력이 있는 품목별로 입고건 + 검사상세를 반환."""
    conn = db.connect()
    try:
        prisms = conn.execute(
            "SELECT pm.id, pm.item_code, pm.spec, pm.prism_type, pm.model, pm.paint_state, "
            "       s.name AS supplier_name "
            "FROM prism_master pm LEFT JOIN supplier s ON s.id=pm.supplier_id "
            "WHERE pm.is_active=1 ORDER BY pm.prism_type, pm.model, pm.item_code").fetchall()

        items = []
        for p in prisms:
            pid = p["id"]
            receipts = conn.execute(
                "SELECT id, receipt_no, receipt_date, received_qty, note FROM receipt "
                "WHERE prism_id=? ORDER BY receipt_date, id", (pid,)).fetchall()
            if not receipts:
                continue

            deliveries = []
            t_recv = t_good = t_def = 0
            for r in receipts:
                lot_ids = [x["id"] for x in conn.execute(
                    "SELECT id FROM lot WHERE receipt_id=?", (r["id"],)).fetchall()]
                insp = None
                if lot_ids:
                    ph = ",".join("?" * len(lot_ids))
                    insp = conn.execute(
                        f"SELECT * FROM inspection WHERE stage='INCOMING' AND lot_id IN ({ph}) LIMIT 1",
                        lot_ids).fetchone()

                if insp:
                    good, defect = insp["good_qty"], insp["defect_qty"]
                    complete = bool(insp["is_complete"])
                    defs = conn.execute(
                        "SELECT ii.name AS name, d.defect_qty AS qty FROM inspection_defect d "
                        "JOIN inspection_item ii ON ii.id=d.inspection_item_id "
                        "WHERE d.inspection_id=? ORDER BY d.defect_qty DESC", (insp["id"],)).fetchall()
                    defects = [{"name": x["name"], "qty": x["qty"]} for x in defs]
                    status = "검사완료" if complete else "검사중"
                    rate = _pct(defect, r["received_qty"])
                    t_good += good
                    t_def += defect
                else:
                    good = defect = rate = None
                    defects = []
                    status = "검사중"

                t_recv += r["received_qty"]
                deliveries.append({
                    "receipt_id": r["id"], "date": r["receipt_date"], "receipt_no": r["receipt_no"],
                    "qty": r["received_qty"], "good": good, "defect": defect,
                    "defect_rate": rate, "status": status, "defects": defects,
                })

            open_note = conn.execute(
                "SELECT note FROM stock_adjustment WHERE prism_id=? AND reason='OPENING' "
                "ORDER BY id DESC LIMIT 1", (pid,)).fetchone()

            items.append({
                "prism_id": pid, "item_code": p["item_code"], "spec": p["spec"],
                "prism_type": p["prism_type"], "model": p["model"], "paint_state": p["paint_state"],
                "supplier_name": p["supplier_name"], "on_hand": _on_hand(conn, pid, p["paint_state"]),
                "total_received": t_recv, "total_good": t_good, "total_defect": t_def,
                "defect_rate": _pct(t_def, t_good + t_def),
                "opening_note": open_note["note"] if open_note else "",
                "deliveries": deliveries,
            })
        return {"ok": True, "items": items}
    finally:
        conn.close()
