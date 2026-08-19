# -*- coding: utf-8 -*-
"""제품마스터(product) 서비스 — 목록/등록/수정/사용여부.

제품(완제품) → 어떤 프리즘(Glass/Plastic) + 대당 소요량 매핑(BOM).
prism_id 가 NULL 이면 '프리즘 미사용 제품' → 구매계획 소비량 0.
"""
from __future__ import annotations

import db
import rules


def list_all() -> list[dict]:
    """프리즘 정보를 함께 조인해 반환."""
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT p.id,p.product_code,p.product_name,p.prism_id,p.prism_per_unit,p.is_active,p.note,"
            "       pm.prism_type AS prism_type, pm.spec AS prism_spec "
            "FROM product p LEFT JOIN prism_master pm ON pm.id=p.prism_id "
            "ORDER BY p.product_code").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _normalize_prism_id(value):
    """빈값/0/none → NULL(미사용)로 정규화."""
    if value in (None, "", "0", 0, "none", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_per_unit(raw, prism_id) -> int:
    """대당 소요량 해석: 미입력이면 기본값(프리즘 사용=1, 미사용=0), 입력값은 0도 그대로 보존.
    (명시적 0을 falsy 로 덮어쓰지 않도록 — 검증이 0을 잡을 수 있게)"""
    if raw is None or str(raw).strip() == "":
        return 1 if prism_id else 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def create(data: dict) -> dict:
    code = (data.get("product_code") or "").strip()
    name = (data.get("product_name") or "").strip()
    prism_id = _normalize_prism_id(data.get("prism_id"))
    per_unit = _resolve_per_unit(data.get("prism_per_unit"), prism_id)
    note = (data.get("note") or "").strip()

    valid, reason = rules.validate_product(code, prism_id, per_unit)
    if not valid:
        return {"ok": False, "error": reason}

    conn = db.connect()
    try:
        ts = db.now_str()
        conn.execute(
            "INSERT INTO product(product_code,product_name,prism_id,prism_per_unit,is_active,note,created_at,updated_at) "
            "VALUES (?,?,?,?,1,?,?,?)", (code, name, prism_id, int(per_unit), note, ts, ts))
        conn.commit()
        return {"ok": True}
    except db.sqlite3.IntegrityError:
        return {"ok": False, "error": f"이미 있는 제품코드입니다: {code}"}
    finally:
        conn.close()


def update(data: dict) -> dict:
    pid = data.get("id")
    code = (data.get("product_code") or "").strip()
    name = (data.get("product_name") or "").strip()
    prism_id = _normalize_prism_id(data.get("prism_id"))
    per_unit = _resolve_per_unit(data.get("prism_per_unit"), prism_id)
    note = (data.get("note") or "").strip()

    valid, reason = rules.validate_product(code, prism_id, per_unit)
    if not valid:
        return {"ok": False, "error": reason}

    conn = db.connect()
    try:
        cur = conn.execute(
            "UPDATE product SET product_code=?,product_name=?,prism_id=?,prism_per_unit=?,note=?,updated_at=? WHERE id=?",
            (code, name, prism_id, int(per_unit), note, db.now_str(), pid))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "대상 제품을 찾을 수 없습니다."}
        return {"ok": True}
    except db.sqlite3.IntegrityError:
        return {"ok": False, "error": f"이미 있는 제품코드입니다: {code}"}
    finally:
        conn.close()


def set_active(data: dict) -> dict:
    pid = data.get("id")
    is_active = 1 if data.get("is_active") else 0
    conn = db.connect()
    try:
        cur = conn.execute(
            "UPDATE product SET is_active=?,updated_at=? WHERE id=?",
            (is_active, db.now_str(), pid))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "대상 제품을 찾을 수 없습니다."}
        return {"ok": True}
    finally:
        conn.close()
