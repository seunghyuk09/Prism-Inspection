# -*- coding: utf-8 -*-
"""업무 규칙 — 단일 소스(Single Source of Truth).

모든 '조건/규칙'은 여기 한 곳에 모은다. 각 서비스(입고/검사/소비…)는 규칙을
직접 만들지 말고 이 파일의 함수를 빌려 쓴다 → 규칙이 두 벌로 갈라져 충돌하는 것을 막는다.

규칙은 두 형태로 제공:
  - 술어(predicate): bool 을 반환 (예: can_create_new_receipt → True/False)
  - 검증(validate_*): (ok: bool, reason: str) 을 반환 (입력값 유효성 + 사유)
"""
from __future__ import annotations

# ── 허용값 집합(enum 역할) ───────────────────────────────────
SUPPLIER_STATUSES = ("ACTIVE", "REMNANT", "STOPPED")
PRISM_TYPES = ("PLASTIC", "GLASS")
PAINT_STATES = ("RAW", "PAINTED", "NONE")   # 미도장 / 도장완료 / 유리·해당없음
INSPECTION_STAGES = ("INCOMING", "POST_PAINT")
INSPECTION_METHODS = ("FULL", "SAMPLING")
LOT_STATUSES = ("CREATED", "INCOMING_DONE", "PAINTING", "POST_PAINT_DONE", "CLOSED")


def ok(reason: str = "") -> tuple[bool, str]:
    return True, reason


def fail(reason: str) -> tuple[bool, str]:
    return False, reason


def _to_int(value, default=0) -> int:
    """숫자 입력을 안전하게 int 로(빈값/문자 방어)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ── 공급사 규칙 ──────────────────────────────────────────────
def is_active_supplier(status: str) -> bool:
    """활성 공급사인가."""
    return status == "ACTIVE"


def can_create_new_receipt(supplier_status: str) -> bool:
    """신규 입고 가능? — 활성(ACTIVE) 공급사만. REMNANT(오프렌)·STOPPED 는 잔량 소진만."""
    return is_active_supplier(supplier_status)


def validate_supplier(name: str, status: str) -> tuple[bool, str]:
    if not (name and name.strip()):
        return fail("공급사명을 입력하세요.")
    if status not in SUPPLIER_STATUSES:
        return fail(f"공급사 상태값이 올바르지 않습니다: {status}")
    return ok()


# ── 프리즘 마스터 규칙 ───────────────────────────────────────
def is_plastic(prism_type: str) -> bool:
    """페인트 단계는 플라스틱만 거친다(글래스는 페인트 없음)."""
    return prism_type == "PLASTIC"


def is_receivable_prism(paint_state: str) -> bool:
    """직접 입고 가능한 프리즘인가? — 도장완료(PAINTED)는 페인트 결과물이라 입고하지 않는다."""
    return paint_state != "PAINTED"


def validate_prism(prism_type: str, spec: str, paint_state: str = "NONE") -> tuple[bool, str]:
    if prism_type not in PRISM_TYPES:
        return fail(f"프리즘 종류가 올바르지 않습니다: {prism_type}")
    if not (spec and spec.strip()):
        return fail("프리즘 규격/명칭을 입력하세요.")
    if paint_state not in PAINT_STATES:
        return fail(f"도장상태가 올바르지 않습니다: {paint_state}")
    # 유리(GLASS)는 도장 단계가 없으므로 RAW/PAINTED 가 어색하다(경고성 차단).
    if prism_type == "GLASS" and paint_state != "NONE":
        return fail("글래스 프리즘의 도장상태는 '해당없음'이어야 합니다.")
    return ok()


# ── 검사항목 규칙 ────────────────────────────────────────────
def validate_inspection_item(name: str, applies_incoming, applies_post) -> tuple[bool, str]:
    if not (name and name.strip()):
        return fail("검사항목 이름을 입력하세요.")
    # 최소 한 단계에는 적용되어야 의미가 있다.
    if not (bool(applies_incoming) or bool(applies_post)):
        return fail("입고검사·페인트후검사 중 최소 한 단계에는 적용되어야 합니다.")
    return ok()


def item_applies_to_stage(item_row, stage: str) -> bool:
    """해당 검사항목이 특정 단계에 적용되는가(불량 기록 가능 여부)."""
    if stage == "INCOMING":
        return bool(item_row["applies_to_incoming"])
    if stage == "POST_PAINT":
        return bool(item_row["applies_to_post_paint"])
    return False


# ── 제품마스터(BOM) 규칙 ─────────────────────────────────────
def product_uses_prism(prism_id) -> bool:
    """이 제품이 프리즘을 사용하는가(미사용 제품은 prism_id=NULL)."""
    return prism_id is not None


def validate_product(product_code: str, prism_id, prism_per_unit) -> tuple[bool, str]:
    if not (product_code and product_code.strip()):
        return fail("제품코드를 입력하세요.")
    if product_uses_prism(prism_id) and _to_int(prism_per_unit) <= 0:
        return fail("프리즘 사용 제품은 대당 소요량이 1 이상이어야 합니다.")
    return ok()


def plan_consumption_qty(planned_qty, prism_per_unit, prism_id) -> int:
    """구매계획 한 줄의 프리즘 소비량 = 생산수량 × 대당 소요량(미사용 제품은 0)."""
    if not product_uses_prism(prism_id):
        return 0
    return _to_int(planned_qty) * _to_int(prism_per_unit)


# ── 수량 정합성 규칙(검사 단계에서 사용 / 지금은 self_check 로 검증) ──
# 미완료(is_complete=False)면 등식은 soft(≤)로 완화 — 페인트후 불량 점진 기록 허용.
def lots_within_receipt(lot_qty_sum, received_qty) -> bool:
    """Σ로트수량 ≤ 입고수량."""
    return _to_int(lot_qty_sum) <= _to_int(received_qty)


def qty_balanced(good_qty, defect_qty, inspected_qty, is_complete: bool) -> bool:
    """양품+불량 == 검사수량(완료) / ≤(미완료)."""
    total = _to_int(good_qty) + _to_int(defect_qty)
    inspected = _to_int(inspected_qty)
    return total == inspected if is_complete else total <= inspected


def defect_sum_matches(defect_qty, defect_sum, is_complete: bool) -> bool:
    """검사.불량 == Σ항목별불량(완료) / ≤(미완료)."""
    if is_complete:
        return _to_int(defect_qty) == _to_int(defect_sum)
    return _to_int(defect_sum) <= _to_int(defect_qty) or _to_int(defect_qty) <= _to_int(defect_sum)


def full_inspection_covers_lot(inspected_qty, lot_qty, method: str) -> bool:
    """전수면 검사수량==로트수량, 샘플이면 검사수량≤로트수량."""
    if method == "FULL":
        return _to_int(inspected_qty) == _to_int(lot_qty)
    return _to_int(inspected_qty) <= _to_int(lot_qty)


def paint_send_valid(sent_qty, incoming_good_qty) -> bool:
    """페인트 발송수량 ≤ 입고검사 양품."""
    return 0 < _to_int(sent_qty) <= _to_int(incoming_good_qty)


def paint_return_valid(returned_sum, sent_qty) -> bool:
    """Σ회수수량 ≤ 발송수량."""
    return _to_int(returned_sum) <= _to_int(sent_qty)


def paint_fully_returned(returned_sum, sent_qty) -> bool:
    """회수 완료? — Σ회수 == 발송."""
    return _to_int(returned_sum) == _to_int(sent_qty)


def can_create_paint_job(prism_type: str, incoming_is_complete: bool) -> bool:
    """페인트 발송 가능? — 플라스틱 + 입고검사 완료."""
    return is_plastic(prism_type) and bool(incoming_is_complete)


def defects_within_base(defect_qty, base) -> bool:
    """불량합은 검사 기준수량(전수=로트/회수수량) 이하여야 한다."""
    return 0 <= _to_int(defect_qty) <= _to_int(base)


def inspection_good_qty(base, defect_qty) -> int:
    """양품 = 검사수량 − 불량합 (전수검사: 불량 전량 선별)."""
    return max(0, _to_int(base) - _to_int(defect_qty))


def stage_needs_paint(prism_type: str, stage: str) -> bool:
    """페인트후검사(POST_PAINT)는 플라스틱만 의미가 있다(글래스는 입고검사만)."""
    if stage == "POST_PAINT":
        return is_plastic(prism_type)
    return True
