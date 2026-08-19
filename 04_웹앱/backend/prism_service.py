# -*- coding: utf-8 -*-
"""프리즘 마스터(prism_master) 서비스 — 목록/등록/수정/사용여부.

ERP 코드 체계 반영:
  - paint_state: RAW(미도장·입고용) / PAINTED(도장완료) / NONE(유리 등)
  - painted_into_id: RAW → 도장완료 코드(페어) 연결
  - supplier_id: 코드가 공급사를 품으므로 프리즘에 공급사를 둔다(입고 시 자동 매핑)
"""
from __future__ import annotations

import db
import rules


def list_all() -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT pm.id, pm.item_code, pm.prism_type, pm.model, pm.spec, pm.unit, pm.is_active, pm.note, "
            "       pm.supplier_id, s.name AS supplier_name, s.status AS supplier_status, "
            "       pm.paint_state, pm.painted_into_id, pp.item_code AS painted_into_code "
            "FROM prism_master pm "
            "LEFT JOIN supplier s ON s.id=pm.supplier_id "
            "LEFT JOIN prism_master pp ON pp.id=pm.painted_into_id "
            "ORDER BY pm.prism_type, pm.model, pm.item_code").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _norm_id(value):
    """빈값 → None, 숫자면 int."""
    if value in (None, "", "0", 0, "none", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fields(data: dict):
    """폼/요청에서 공통 필드 추출·정규화."""
    prism_type = (data.get("prism_type") or "").strip()
    paint_state = (data.get("paint_state") or "NONE").strip() or "NONE"
    painted_into_id = _norm_id(data.get("painted_into_id"))
    # 도장완료(PAINTED)/유리(NONE) 는 페어 대상이 아님 → 페어 비움
    if paint_state != "RAW":
        painted_into_id = None
    return {
        "item_code": (data.get("item_code") or "").strip() or None,
        "prism_type": prism_type,
        "model": (data.get("model") or "").strip(),
        "spec": (data.get("spec") or "").strip(),
        "supplier_id": _norm_id(data.get("supplier_id")),
        "paint_state": paint_state,
        "painted_into_id": painted_into_id,
        "unit": (data.get("unit") or "EA").strip(),
        "note": (data.get("note") or "").strip(),
    }


def create(data: dict) -> dict:
    f = _fields(data)
    valid, reason = rules.validate_prism(f["prism_type"], f["spec"], f["paint_state"])
    if not valid:
        return {"ok": False, "error": reason}
    conn = db.connect()
    try:
        ts = db.now_str()
        conn.execute(
            "INSERT INTO prism_master(item_code,prism_type,model,spec,supplier_id,paint_state,painted_into_id,"
            "unit,is_active,note,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?,?)",
            (f["item_code"], f["prism_type"], f["model"], f["spec"], f["supplier_id"],
             f["paint_state"], f["painted_into_id"], f["unit"], f["note"], ts, ts))
        conn.commit()
        return {"ok": True}
    except db.sqlite3.IntegrityError:
        return {"ok": False, "error": f"이미 사용 중인 품목코드입니다: {f['item_code']}"}
    finally:
        conn.close()


def update(data: dict) -> dict:
    pid = data.get("id")
    f = _fields(data)
    valid, reason = rules.validate_prism(f["prism_type"], f["spec"], f["paint_state"])
    if not valid:
        return {"ok": False, "error": reason}
    conn = db.connect()
    try:
        cur = conn.execute(
            "UPDATE prism_master SET item_code=?,prism_type=?,model=?,spec=?,supplier_id=?,paint_state=?,"
            "painted_into_id=?,unit=?,note=?,updated_at=? WHERE id=?",
            (f["item_code"], f["prism_type"], f["model"], f["spec"], f["supplier_id"], f["paint_state"],
             f["painted_into_id"], f["unit"], f["note"], db.now_str(), pid))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "대상 프리즘을 찾을 수 없습니다."}
        return {"ok": True}
    except db.sqlite3.IntegrityError:
        return {"ok": False, "error": f"이미 사용 중인 품목코드입니다: {f['item_code']}"}
    finally:
        conn.close()


def set_active(data: dict) -> dict:
    """사용여부 토글(0/1)."""
    pid = data.get("id")
    is_active = 1 if data.get("is_active") else 0
    conn = db.connect()
    try:
        cur = conn.execute("UPDATE prism_master SET is_active=?,updated_at=? WHERE id=?",
                           (is_active, db.now_str(), pid))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "대상 프리즘을 찾을 수 없습니다."}
        return {"ok": True}
    finally:
        conn.close()
