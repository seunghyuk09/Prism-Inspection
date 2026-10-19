# -*- coding: utf-8 -*-
"""재고(잔량) 서비스 — 프리즘 코드별 현재고 계산 + 기초재고/보정.

도장상태별 잔량 계산식:
  - NONE(유리)   : 기초보정 + Σ입고검사양품 − Σ소비
  - RAW(미도장)  : 기초보정 + Σ입고검사양품 − Σ페인트발송 − Σ인쇄투입 − Σ소비
  - PAINTED(도장): 기초보정 + Σ(페어 RAW 로트의 페인트후 양품) + Σ인쇄산출 − Σ소비
페인트후 양품이 '도장완료 코드' 재고로 전환되는 페어(painted_into_id)를 활용한다.
"""
from __future__ import annotations

import db
import rules

# unusable_stock.category 값. '불량' 은 사내 불량창고, 아래는 사급으로 외주(우경)에 가 있는 양.
# 둘 다 현재고엔 포함되지만 가용재고에서는 뺀다.
VENDOR_HELD_CATEGORY = "우경보관"


def _scalar(conn, sql, params):
    return conn.execute(sql, params).fetchone()["s"]


def stock_status(data=None) -> dict:
    """프리즘 코드별 현재고 목록."""
    conn = db.connect()
    try:
        prisms = conn.execute(
            "SELECT pm.id, pm.item_code, pm.prism_type, pm.model, pm.spec, pm.paint_state, "
            "       s.name AS supplier_name, s.status AS supplier_status, pp.item_code AS painted_into_code "
            "FROM prism_master pm LEFT JOIN supplier s ON s.id=pm.supplier_id "
            "LEFT JOIN prism_master pp ON pp.id=pm.painted_into_id "
            "WHERE pm.is_active=1 ORDER BY pm.prism_type, pm.model, pm.item_code").fetchall()
        rows = []
        for p in prisms:
            cid = p["id"]
            adj = _scalar(conn, "SELECT COALESCE(SUM(qty),0) s FROM stock_adjustment WHERE prism_id=?", (cid,))
            consumed = _scalar(conn, "SELECT COALESCE(SUM(qty),0) s FROM consumption WHERE prism_id=?", (cid,))
            unusable = _scalar(conn,
                "SELECT COALESCE(SUM(qty),0) s FROM unusable_stock WHERE prism_id=? AND COALESCE(category,'') <> ?",
                (cid, VENDOR_HELD_CATEGORY))
            vendor_held = _scalar(conn,
                "SELECT COALESCE(SUM(qty),0) s FROM unusable_stock WHERE prism_id=? AND category=?",
                (cid, VENDOR_HELD_CATEGORY))
            incoming_good = _scalar(conn,
                "SELECT COALESCE(SUM(i.good_qty),0) s FROM inspection i "
                "JOIN lot l ON l.id=i.lot_id JOIN receipt r ON r.id=l.receipt_id "
                "WHERE i.stage='INCOMING' AND r.prism_id=?", (cid,))
            sent_paint = _scalar(conn,
                "SELECT COALESCE(SUM(pj.sent_qty),0) s FROM paint_job pj "
                "JOIN lot l ON l.id=pj.lot_id JOIN receipt r ON r.id=l.receipt_id WHERE r.prism_id=?", (cid,))
            painted_in = _scalar(conn,
                "SELECT COALESCE(SUM(i.good_qty),0) s FROM inspection i "
                "JOIN lot l ON l.id=i.lot_id JOIN receipt r ON r.id=l.receipt_id "
                "JOIN prism_master pm ON pm.id=r.prism_id "
                "WHERE i.stage='POST_PAINT' AND pm.painted_into_id=?", (cid,))
            # 인쇄 작업: 투입분은 RAW 에서 빠지고, 산출분은 With Paint 로 들어온다
            printed_input = _scalar(conn,
                "SELECT COALESCE(SUM(input_qty),0) s FROM print_job WHERE raw_prism_id=?", (cid,))
            printed_output = _scalar(conn,
                "SELECT COALESCE(SUM(output_qty),0) s FROM print_job WHERE painted_prism_id=?", (cid,))

            ps = p["paint_state"]
            if ps == "PAINTED":
                produced = painted_in + printed_output
                on_hand = adj + produced - consumed
                basis = "페인트후 양품 + 인쇄 산출"
            elif ps == "RAW":
                produced = incoming_good
                on_hand = adj + incoming_good - sent_paint - printed_input - consumed
                basis = "입고양품 − 페인트발송 − 인쇄투입"
            else:  # NONE (유리)
                produced, on_hand, basis = incoming_good, adj + incoming_good - consumed, "입고검사 양품"

            rows.append({**dict(p), "opening_adj": adj, "produced": produced,
                         "printed_input": printed_input, "printed_output": printed_output,
                         "sent_paint": sent_paint, "consumed": consumed, "on_hand": on_hand, "basis": basis,
                         "unusable": unusable, "vendor_held": vendor_held,
                         "available": on_hand - unusable - vendor_held})
        return {"ok": True, "items": rows}
    finally:
        conn.close()


def add_adjustment(data: dict) -> dict:
    """기초재고/수기 보정 추가(부호 있는 수량)."""
    prism_id = data.get("prism_id")
    qty = rules._to_int(data.get("qty"))
    reason = (data.get("reason") or "OPENING").strip()
    if reason not in ("OPENING", "MANUAL"):
        reason = "MANUAL"
    if not prism_id:
        return {"ok": False, "error": "프리즘을 선택하세요."}
    if qty == 0:
        return {"ok": False, "error": "수량을 입력하세요 (+ 기초재고 / - 감모)."}
    conn = db.connect()
    try:
        ts = db.now_str()
        conn.execute(
            "INSERT INTO stock_adjustment(prism_id,qty,reason,adjusted_at,note,created_at) VALUES (?,?,?,?,?,?)",
            (prism_id, qty, reason, (data.get("adjusted_at") or ts[:10]).strip(), (data.get("note") or "").strip(), ts))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
