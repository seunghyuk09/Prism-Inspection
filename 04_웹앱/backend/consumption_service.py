# -*- coding: utf-8 -*-
"""생산 소모 서비스 — 제품을 만들 때 쓰인 With Paint 프리즘을 차감하고 이력을 남긴다.

입력 방법 두 가지:
  - 제품 기준: 제품 + 생산수량 → 제품마스터의 개당소요량으로 소모량 자동 계산
  - 직접 입력: 프리즘 + 소모수량
구매계획/수불부 임포트로 들어온 소비(PLAN)도 같은 이력에서 함께 본다.
"""
from __future__ import annotations

import db
import rules

SOURCE_LABEL = {"PLAN": "구매계획", "MANUAL": "직접입력", "ADJUST": "보정"}


def consumable_products(data=None) -> dict:
    """소모 입력에 쓸 제품 목록(프리즘이 연결된 것만)."""
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT p.id, p.product_code, p.product_name, p.prism_per_unit, "
            "       pm.id AS prism_id, pm.item_code AS prism_code, pm.spec AS prism_spec "
            "FROM product p JOIN prism_master pm ON pm.id=p.prism_id "
            "WHERE p.is_active=1 ORDER BY p.product_code").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_consumption(data=None) -> dict:
    """소비 이력(최근순) + 품목별 합계."""
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT c.id, c.consumed_at, c.qty, c.source, c.note, c.created_at, "
            "       pm.item_code, pm.spec, pm.paint_state "
            "FROM consumption c JOIN prism_master pm ON pm.id=c.prism_id "
            "ORDER BY c.consumed_at DESC, c.id DESC LIMIT 500").fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["source_label"] = SOURCE_LABEL.get(d["source"], d["source"])
            d["can_delete"] = d["source"] == "MANUAL"
            items.append(d)
        return items
    finally:
        conn.close()


def save(data: dict) -> dict:
    """생산 소모 등록 — 제품 기준(product_id + produced_qty) 또는 직접(prism_id + qty)."""
    consumed_at = (data.get("consumed_at") or "").strip()
    if not consumed_at:
        return {"ok": False, "error": "소모일을 입력하세요."}

    product_id = data.get("product_id")
    prism_id = data.get("prism_id")
    qty = rules._to_int(data.get("qty"))
    produced_qty = rules._to_int(data.get("produced_qty"))
    note = (data.get("note") or "").strip()

    conn = db.connect()
    try:
        if product_id:
            prod = conn.execute(
                "SELECT id, product_code, product_name, prism_id, prism_per_unit "
                "FROM product WHERE id=?", (product_id,)).fetchone()
            if not prod:
                return {"ok": False, "error": "제품을 찾을 수 없습니다."}
            if not prod["prism_id"]:
                return {"ok": False, "error": f"{prod['product_code']} 에 프리즘이 연결돼 있지 않습니다."}
            if produced_qty <= 0:
                return {"ok": False, "error": "생산수량을 입력하세요."}
            prism_id = prod["prism_id"]
            qty = rules.plan_consumption_qty(produced_qty, prod["prism_per_unit"], prism_id)
            if not note:
                note = f"{prod['product_code']} 생산 {produced_qty:,}개 × {prod['prism_per_unit']}"

        if not prism_id:
            return {"ok": False, "error": "제품 또는 프리즘을 선택하세요."}
        if qty <= 0:
            return {"ok": False, "error": "소모 수량이 0 입니다."}

        ts = db.now_str()
        cur = conn.execute(
            "INSERT INTO consumption(prism_id,source,qty,consumed_at,note,created_at) "
            "VALUES (?,?,?,?,?,?)", (prism_id, "MANUAL", qty, consumed_at, note, ts))
        conn.commit()
        return {"ok": True, "id": cur.lastrowid, "qty": qty}
    finally:
        conn.close()


def delete(data: dict) -> dict:
    """직접입력(MANUAL) 소비만 삭제. 구매계획분은 해당 화면에서 취소해야 한다."""
    cid = data.get("id")
    conn = db.connect()
    try:
        row = conn.execute("SELECT source FROM consumption WHERE id=?", (cid,)).fetchone()
        if not row:
            return {"ok": False, "error": "소비 기록을 찾을 수 없습니다."}
        if row["source"] != "MANUAL":
            return {"ok": False, "error": "구매계획·수불부로 들어온 소비는 여기서 지울 수 없습니다."}
        conn.execute("DELETE FROM consumption WHERE id=?", (cid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
