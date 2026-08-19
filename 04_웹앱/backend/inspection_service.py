# -*- coding: utf-8 -*-
"""검사(inspection) 서비스 — 입고검사(INCOMING) · 페인트후검사(POST_PAINT).

전수검사 기준:
  - 검사수량(base): 입고검사=로트수량, 페인트후검사=페인트 회수합계
  - 양품 = 검사수량 − 불량합(불량 전량 선별)  → rules.inspection_good_qty
  - 불량합 = Σ항목별 불량(롱포맷 inspection_defect)
미완료(is_complete=0) 허용: 페인트후 불량을 나중에 점진 기록. 완료 시에만 hard 게이팅.
"""
from __future__ import annotations

import db
import rules


# ── 내부 조회 헬퍼 ───────────────────────────────────────────
def _lot_row(conn, lot_id):
    return conn.execute(
        "SELECT l.id, l.lot_no, l.lot_qty, l.status, r.receipt_no, "
        "       s.name AS supplier_name, pm.prism_type, pm.spec AS prism_spec "
        "FROM lot l JOIN receipt r ON r.id=l.receipt_id "
        "JOIN supplier s ON s.id=r.supplier_id JOIN prism_master pm ON pm.id=r.prism_id "
        "WHERE l.id=?", (lot_id,)).fetchone()


def _inspection(conn, lot_id, stage):
    return conn.execute("SELECT * FROM inspection WHERE lot_id=? AND stage=?", (lot_id, stage)).fetchone()


def _defects_map(conn, inspection_id):
    rows = conn.execute("SELECT inspection_item_id, defect_qty FROM inspection_defect WHERE inspection_id=?",
                        (inspection_id,)).fetchall()
    return {r["inspection_item_id"]: r["defect_qty"] for r in rows}


def _paint_sums(conn, lot_id):
    """로트의 페인트 발송합·회수합."""
    sent = conn.execute("SELECT COALESCE(SUM(sent_qty),0) AS s FROM paint_job WHERE lot_id=?",
                        (lot_id,)).fetchone()["s"]
    ret = conn.execute(
        "SELECT COALESCE(SUM(pr.returned_qty),0) AS s FROM paint_return pr "
        "JOIN paint_job pj ON pj.id=pr.paint_job_id WHERE pj.lot_id=?", (lot_id,)).fetchone()["s"]
    return sent, ret


def _base_qty(conn, lot, stage):
    """검사 기준수량(전수): 입고검사=로트수량, 페인트후검사=회수합계."""
    if stage == "INCOMING":
        return lot["lot_qty"]
    _, returned = _paint_sums(conn, lot["id"])
    return returned


def _items_for_stage(conn, stage):
    col = "applies_to_incoming" if stage == "INCOMING" else "applies_to_post_paint"
    rows = conn.execute(
        f"SELECT id,name,category,sort_order FROM inspection_item WHERE is_active=1 AND {col}=1 "
        "ORDER BY sort_order,id").fetchall()
    return [dict(r) for r in rows]


def _pack_inspection(conn, lot, stage):
    """한 단계 검사 상태를 화면용 dict 로."""
    insp = _inspection(conn, lot["id"], stage)
    base = _base_qty(conn, lot, stage)
    items = _items_for_stage(conn, stage)
    defects = _defects_map(conn, insp["id"]) if insp else {}
    defect_qty = sum(defects.values())
    return {
        "exists": insp is not None,
        "id": insp["id"] if insp else None,
        "method": insp["method"] if insp else "FULL",
        "start_date": insp["start_date"] if insp else "",
        "end_date": insp["end_date"] if insp else "",
        "inspector": insp["inspector"] if insp else "",
        "judgment": insp["judgment"] if insp else "",
        "is_complete": bool(insp["is_complete"]) if insp else False,
        "note": insp["note"] if insp else "",
        "base_qty": base,                         # 검사 기준수량(전수)
        "defect_qty": defect_qty,
        "good_qty": rules.inspection_good_qty(base, defect_qty),
        "items": items,                           # 이 단계에 적용되는 검사항목
        "defects": defects,                       # {item_id: qty}
    }


# ── 화면용 전체 파이프라인 ───────────────────────────────────
def get_for_lot(data) -> dict:
    lot_id = data.get("id") if isinstance(data, dict) else data
    conn = db.connect()
    try:
        lot = _lot_row(conn, lot_id)
        if not lot:
            return {"ok": False, "error": "로트를 찾을 수 없습니다."}
        is_plastic = rules.is_plastic(lot["prism_type"])

        incoming = _pack_inspection(conn, lot, "INCOMING")
        sent_sum, returned_sum = _paint_sums(conn, lot["id"])

        # 페인트 작업 목록(발송 + 분할회수)
        jobs = []
        for j in conn.execute("SELECT * FROM paint_job WHERE lot_id=? ORDER BY id", (lot["id"],)).fetchall():
            rets = [dict(r) for r in conn.execute(
                "SELECT id,returned_date,returned_qty,note FROM paint_return WHERE paint_job_id=? ORDER BY id",
                (j["id"],)).fetchall()]
            rsum = sum(r["returned_qty"] for r in rets)
            jobs.append({**dict(j), "returns": rets, "returned_sum": rsum})

        result = {
            "ok": True,
            "lot": dict(lot),
            "is_plastic": is_plastic,
            "incoming": incoming,
            "paint": {
                "jobs": jobs, "sent_sum": sent_sum, "returned_sum": returned_sum,
                # 발송 가능 잔량 = 입고검사 양품 − 이미 발송
                "sendable": max(0, incoming["good_qty"] - sent_sum) if incoming["is_complete"] else 0,
                "can_send": is_plastic and incoming["is_complete"],
            },
        }
        if is_plastic:
            result["post_paint"] = _pack_inspection(conn, lot, "POST_PAINT")
            final_good = result["post_paint"]["good_qty"] if result["post_paint"]["exists"] else None
        else:
            result["post_paint"] = None
            final_good = incoming["good_qty"] if incoming["is_complete"] else None
        result["final_good"] = final_good
        return result
    finally:
        conn.close()


def list_lots(data=None) -> list[dict]:
    """검사 작업대용 로트 목록 + 진행상태."""
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT l.id, l.lot_no, l.lot_qty, l.status, r.receipt_no, pm.prism_type, s.name AS supplier_name, "
            " (SELECT is_complete FROM inspection WHERE lot_id=l.id AND stage='INCOMING') AS incoming_done, "
            " (SELECT is_complete FROM inspection WHERE lot_id=l.id AND stage='POST_PAINT') AS post_done, "
            " (SELECT good_qty FROM inspection WHERE lot_id=l.id AND stage='INCOMING') AS incoming_good, "
            " (SELECT COALESCE(SUM(sent_qty),0) FROM paint_job WHERE lot_id=l.id) AS sent_sum, "
            " (SELECT COALESCE(SUM(pr.returned_qty),0) FROM paint_return pr "
            "  JOIN paint_job pj ON pj.id=pr.paint_job_id WHERE pj.lot_id=l.id) AS returned_sum "
            "FROM lot l JOIN receipt r ON r.id=l.receipt_id "
            "JOIN supplier s ON s.id=r.supplier_id JOIN prism_master pm ON pm.id=r.prism_id "
            "ORDER BY l.id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── 저장(등록/수정) ──────────────────────────────────────────
def save(data: dict) -> dict:
    lot_id = data.get("lot_id")
    stage = (data.get("stage") or "").strip()
    if stage not in rules.INSPECTION_STAGES:
        return {"ok": False, "error": "검사 단계가 올바르지 않습니다."}
    method = (data.get("method") or "FULL").strip()
    start_date = (data.get("start_date") or "").strip()
    end_date = (data.get("end_date") or "").strip()
    inspector = (data.get("inspector") or "").strip()
    note = (data.get("note") or "").strip()
    is_complete = 1 if data.get("is_complete") else 0
    judgment = (data.get("judgment") or "").strip() or None
    defects = data.get("defects") or []   # [{item_id, qty}]

    conn = db.connect()
    try:
        lot = _lot_row(conn, lot_id)
        if not lot:
            return {"ok": False, "error": "로트를 찾을 수 없습니다."}
        # 글래스는 페인트후검사 없음
        if not rules.stage_needs_paint(lot["prism_type"], stage):
            return {"ok": False, "error": "글래스 프리즘은 페인트후검사가 없습니다."}

        base = _base_qty(conn, lot, stage)
        if stage == "POST_PAINT" and base <= 0:
            return {"ok": False, "error": "페인트 회수 수량이 있어야 페인트후검사를 기록할 수 있습니다."}

        # 검사항목 적용성 검증 + 불량합 계산
        valid_item_ids = {it["id"] for it in _items_for_stage(conn, stage)}
        clean_defects = []
        defect_qty = 0
        for d in defects:
            iid = d.get("item_id")
            qty = rules._to_int(d.get("qty"))
            if qty <= 0:
                continue
            if iid not in valid_item_ids:
                return {"ok": False, "error": f"이 단계에 적용되지 않는 검사항목이 포함되어 있습니다(item {iid})."}
            clean_defects.append((iid, qty))
            defect_qty += qty

        if not rules.defects_within_base(defect_qty, base):
            return {"ok": False, "error": f"불량 합계({defect_qty})가 검사수량({base})을 초과할 수 없습니다."}

        inspected_qty = base                       # 전수검사
        good_qty = rules.inspection_good_qty(base, defect_qty)

        # 완료 게이팅(hard) — 전수: 검사수량==기준, 양품+불량==검사수량
        if is_complete:
            if not rules.full_inspection_covers_lot(inspected_qty, base, method):
                return {"ok": False, "error": "전수검사 기준수량과 일치하지 않습니다."}
            if not rules.qty_balanced(good_qty, defect_qty, inspected_qty, True):
                return {"ok": False, "error": "양품+불량이 검사수량과 맞지 않습니다."}
            if not judgment:
                judgment = "PASS"

        ts = db.now_str()
        insp = _inspection(conn, lot_id, stage)
        if insp:
            conn.execute(
                "UPDATE inspection SET method=?,start_date=?,end_date=?,inspected_qty=?,good_qty=?,defect_qty=?,"
                "judgment=?,inspector=?,is_complete=?,note=?,updated_at=? WHERE id=?",
                (method, start_date, end_date, inspected_qty, good_qty, defect_qty,
                 judgment, inspector, is_complete, note, ts, insp["id"]))
            inspection_id = insp["id"]
            conn.execute("DELETE FROM inspection_defect WHERE inspection_id=?", (inspection_id,))
        else:
            cur = conn.execute(
                "INSERT INTO inspection(lot_id,stage,method,start_date,end_date,inspected_qty,good_qty,defect_qty,"
                "judgment,inspector,is_complete,note,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (lot_id, stage, method, start_date, end_date, inspected_qty, good_qty, defect_qty,
                 judgment, inspector, is_complete, note, ts, ts))
            inspection_id = cur.lastrowid

        for iid, qty in clean_defects:
            conn.execute("INSERT INTO inspection_defect(inspection_id,inspection_item_id,defect_qty) VALUES (?,?,?)",
                         (inspection_id, iid, qty))

        # 로트 상태 갱신
        if is_complete and stage == "INCOMING" and lot["status"] == "CREATED":
            conn.execute("UPDATE lot SET status='INCOMING_DONE',updated_at=? WHERE id=?", (ts, lot_id))
        if is_complete and stage == "POST_PAINT":
            conn.execute("UPDATE lot SET status='POST_PAINT_DONE',updated_at=? WHERE id=?", (ts, lot_id))

        conn.commit()
        return {"ok": True, "good_qty": good_qty, "defect_qty": defect_qty, "inspected_qty": inspected_qty}
    finally:
        conn.close()
