# -*- coding: utf-8 -*-
"""집계(report) 서비스 — 로트별/공급사별/항목별 집계 + 엑셀 다운로드.

요구 5: 입고일·로트별 양품/불량/검사항목별 불량률, 수율.
엑셀: 로트 1건 검사이력(건별 다운로드) + 전체 집계.
"""
from __future__ import annotations

import io

import db
import inspection_service


def _rate(defect, base):
    return round(defect / base * 100, 2) if base else 0.0


# ── 화면용 집계 ──────────────────────────────────────────────
def summary(data=None) -> dict:
    conn = db.connect()
    try:
        # 로트별(입고검사 있는 로트)
        lots = conn.execute(
            "SELECT l.id, l.lot_no, l.lot_qty, r.receipt_no, r.receipt_date, "
            "       pm.item_code, pm.prism_type, pm.model, s.name AS supplier_name, "
            "       inc.start_date inc_s, inc.end_date inc_e, inc.inspected_qty inc_insp, inc.good_qty inc_good, inc.defect_qty inc_def, inc.is_complete inc_c, "
            "       post.good_qty post_good, post.defect_qty post_def, post.inspected_qty post_insp, post.is_complete post_c, "
            "       (SELECT COALESCE(SUM(sent_qty),0) FROM paint_job WHERE lot_id=l.id) sent, "
            "       (SELECT COALESCE(SUM(pr.returned_qty),0) FROM paint_return pr JOIN paint_job pj ON pj.id=pr.paint_job_id WHERE pj.lot_id=l.id) returned "
            "FROM lot l JOIN receipt r ON r.id=l.receipt_id JOIN prism_master pm ON pm.id=r.prism_id JOIN supplier s ON s.id=r.supplier_id "
            "LEFT JOIN inspection inc ON inc.lot_id=l.id AND inc.stage='INCOMING' "
            "LEFT JOIN inspection post ON post.lot_id=l.id AND post.stage='POST_PAINT' "
            "WHERE inc.id IS NOT NULL ORDER BY r.receipt_date DESC, l.id DESC").fetchall()
        by_lot = []
        for r in lots:
            d = dict(r)
            final_good = d["post_good"] if d["post_good"] is not None else d["inc_good"]
            by_lot.append({
                "lot_id": d["id"], "lot_no": d["lot_no"], "lot_qty": d["lot_qty"],
                "item_code": d["item_code"], "prism_type": d["prism_type"], "model": d["model"],
                "supplier_name": d["supplier_name"], "receipt_date": d["receipt_date"],
                "inc_period": f"{d['inc_s'] or ''} ~ {d['inc_e'] or '(진행중)'}",
                "inc_good": d["inc_good"], "inc_defect": d["inc_def"],
                "inc_rate": _rate(d["inc_def"] or 0, d["inc_insp"] or 0),
                "sent": d["sent"], "returned": d["returned"],
                "post_good": d["post_good"], "post_defect": d["post_def"],
                "post_rate": _rate(d["post_def"] or 0, d["post_insp"] or 0),
                "final_good": final_good,
                "yield": _rate(final_good or 0, d["lot_qty"]),
                "complete": bool(d["inc_c"]) and (d["post_c"] is None or bool(d["post_c"])),
            })

        # 로트 표기 간소화: 연월일_L## (그날 생성순으로 순번 → 같은 날 여러 로트도 유일)
        by_ymd = {}
        for b in by_lot:
            by_ymd.setdefault((b["receipt_date"] or "").replace("-", ""), []).append(b)
        for ymd, group in by_ymd.items():
            for seq, b in enumerate(sorted(group, key=lambda x: x["lot_id"]), start=1):
                b["lot_label"] = f"{ymd}_L{seq:02d}" if ymd else b["lot_no"]

        # 공급사별 — 입고합계와 검사합계를 따로 집계 후 병합(조인 중복합산 방지)
        recv = {r["supplier_id"]: r["s"] for r in conn.execute(
            "SELECT supplier_id, COALESCE(SUM(received_qty),0) s FROM receipt GROUP BY supplier_id").fetchall()}
        insp = {r["supplier_id"]: r for r in conn.execute(
            "SELECT r.supplier_id, COALESCE(SUM(inc.inspected_qty),0) inspected, "
            "       COALESCE(SUM(inc.good_qty),0) good, COALESCE(SUM(inc.defect_qty),0) defect "
            "FROM inspection inc JOIN lot l ON l.id=inc.lot_id JOIN receipt r ON r.id=l.receipt_id "
            "WHERE inc.stage='INCOMING' GROUP BY r.supplier_id").fetchall()}
        by_supplier = []
        for s in conn.execute("SELECT id,name FROM supplier ORDER BY name").fetchall():
            i = insp.get(s["id"])
            inspected = i["inspected"] if i else 0
            good = i["good"] if i else 0
            defect = i["defect"] if i else 0
            by_supplier.append({"supplier_name": s["name"], "received": recv.get(s["id"], 0),
                                "inspected": inspected, "good": good, "defect": defect,
                                "defect_rate": _rate(defect, inspected)})

        # 항목별 불량률(단계 분리)
        inc_total = conn.execute("SELECT COALESCE(SUM(inspected_qty),0) s FROM inspection WHERE stage='INCOMING'").fetchone()["s"]
        post_total = conn.execute("SELECT COALESCE(SUM(inspected_qty),0) s FROM inspection WHERE stage='POST_PAINT'").fetchone()["s"]
        items = conn.execute("SELECT id,name,category FROM inspection_item ORDER BY sort_order,id").fetchall()
        by_item = []
        for it in items:
            inc_def = conn.execute(
                "SELECT COALESCE(SUM(idf.defect_qty),0) s FROM inspection_defect idf "
                "JOIN inspection i ON i.id=idf.inspection_id WHERE i.stage='INCOMING' AND idf.inspection_item_id=?", (it["id"],)).fetchone()["s"]
            post_def = conn.execute(
                "SELECT COALESCE(SUM(idf.defect_qty),0) s FROM inspection_defect idf "
                "JOIN inspection i ON i.id=idf.inspection_id WHERE i.stage='POST_PAINT' AND idf.inspection_item_id=?", (it["id"],)).fetchone()["s"]
            by_item.append({
                "name": it["name"], "category": it["category"],
                "inc_defect": inc_def, "inc_rate": _rate(inc_def, inc_total),
                "post_defect": post_def, "post_rate": _rate(post_def, post_total),
            })

        return {"ok": True, "by_lot": by_lot, "by_supplier": by_supplier, "by_item": by_item,
                "totals": {"inc_inspected": inc_total, "post_inspected": post_total, "lot_count": len(by_lot)}}
    finally:
        conn.close()


# ── 엑셀 빌드 헬퍼 ───────────────────────────────────────────
def _wb_bytes(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _style_header(ws, cells, fill="D9E1F2"):
    from openpyxl.styles import Font, PatternFill, Alignment
    for c in cells:
        ws[c].font = Font(name="맑은 고딕", bold=True, size=10)
        ws[c].fill = PatternFill("solid", fgColor=fill)
        ws[c].alignment = Alignment(horizontal="center", vertical="center")


def _simple_lot_label(lot_no):
    """RCV-YYYYMMDD-###-L## → YYYYMMDD_L## (없으면 원본)."""
    parts = (lot_no or "").split("-")
    ymd = next((p for p in parts if len(p) == 8 and p.isdigit()), None)
    lsuf = parts[-1] if parts and parts[-1].upper().startswith("L") else None
    return f"{ymd}_{lsuf}" if ymd and lsuf else (lot_no or "")


def lot_excel(lot_id, label=None):
    """로트 1건 검사이력 엑셀(건별 다운로드) — 테두리/음영/정렬 적용. (bytes, filename) 반환."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.cell.cell import MergedCell

    d = inspection_service.get_for_lot({"id": lot_id})
    if not d.get("ok"):
        return None, None
    L = d["lot"]
    disp = label or _simple_lot_label(L["lot_no"])   # 집계와 동일한 간단 라벨

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "검사이력"
    ws.column_dimensions["A"].width = 16
    for col in "BCDEF":
        ws.column_dimensions[col].width = 15

    FONT = "맑은 고딕"
    thin = Side(style="thin", color="8AA0C8")
    BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
    FILL_SECT = PatternFill("solid", fgColor="D9E1F2")   # 섹션 제목
    FILL_LABEL = PatternFill("solid", fgColor="EEF2FA")   # 라벨
    FILL_HEAD = PatternFill("solid", fgColor="F3F6FC")   # 표 헤더
    C = Alignment(horizontal="center", vertical="center")
    LFT = Alignment(horizontal="left", vertical="center")
    RGT = Alignment(horizontal="right", vertical="center")
    MAXC = 6  # A..F

    def cell(coord, val=None, bold=False, size=10, fill=None, align=LFT):
        c = ws[coord]
        if not isinstance(c, MergedCell):   # 병합셀(앵커 외)은 value 읽기전용
            c.value = val
        c.font = Font(name=FONT, bold=bold, size=size)
        c.border = BORDER
        c.alignment = align
        if fill:
            c.fill = fill
        return c

    def fill_row(rownum, fill):
        # 병합 여백칸까지 테두리·음영을 채운다(값은 건드리지 않음)
        for col in "ABCDEF":
            c = ws[f"{col}{rownum}"]
            c.border = BORDER
            c.fill = fill

    r = 1
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=MAXC)
    cell("A1", f"프리즘 검사이력 — {disp}", bold=True, size=14, fill=FILL_SECT, align=C)
    fill_row(1, FILL_SECT)
    ws.row_dimensions[1].height = 26
    r = 3

    def kv(l1, v1, l2=None, v2=None):
        """A=라벨 B:C=값 / D=라벨 E:F=값 (테두리·병합)."""
        nonlocal r
        cell(f"A{r}", l1, bold=True, fill=FILL_LABEL, align=C)
        ws.merge_cells(f"B{r}:C{r}"); cell(f"B{r}", v1, align=LFT); cell(f"C{r}")
        if l2 is not None:
            cell(f"D{r}", l2, bold=True, fill=FILL_LABEL, align=C)
            ws.merge_cells(f"E{r}:F{r}"); cell(f"E{r}", v2, align=LFT); cell(f"F{r}")
        else:
            ws.merge_cells(f"D{r}:F{r}"); cell(f"D{r}"); cell(f"E{r}"); cell(f"F{r}")
        r += 1

    kv("로트번호", disp, "프리즘", f"{L.get('prism_type','')} {L.get('prism_spec','')}".strip())
    kv("공급사", L.get("supplier_name", ""), "로트수량", L.get("lot_qty", ""))
    kv("입고번호", L.get("receipt_no", ""))
    r += 1

    def sect(title):
        nonlocal r
        ws.merge_cells(f"A{r}:F{r}")
        cell(f"A{r}", title, bold=True, size=11, fill=FILL_SECT, align=LFT)
        fill_row(r, FILL_SECT)
        r += 1

    def insp_block(title, p):
        nonlocal r
        sect(title)
        kv("검사기간", f"{p.get('start_date','') or ''} ~ {p.get('end_date','') or '(진행중)'}", "검사수량", p.get("base_qty", 0))
        kv("양품", p.get("good_qty", 0), "불량", p.get("defect_qty", 0))
        # 항목 표 헤더 (A/B/C), D:F 병합 여백
        cell(f"A{r}", "검사항목", bold=True, fill=FILL_HEAD, align=C)
        cell(f"B{r}", "불량수량", bold=True, fill=FILL_HEAD, align=C)
        cell(f"C{r}", "불량률(%)", bold=True, fill=FILL_HEAD, align=C)
        ws.merge_cells(f"D{r}:F{r}"); cell(f"D{r}", fill=FILL_HEAD); cell(f"E{r}", fill=FILL_HEAD); cell(f"F{r}", fill=FILL_HEAD)
        r += 1
        base = p.get("base_qty", 0) or 0
        items = p.get("items", [])
        if not items:
            ws.merge_cells(f"A{r}:F{r}"); cell(f"A{r}", "(검사 항목 없음)", align=C); [cell(f"{c}{r}") for c in "BCDEF"]; r += 1
        for it in items:
            q = p.get("defects", {}).get(it["id"], 0)
            cell(f"A{r}", it["name"], align=LFT)
            cell(f"B{r}", q, align=RGT)
            cell(f"C{r}", _rate(q, base), align=RGT)
            ws.merge_cells(f"D{r}:F{r}"); cell(f"D{r}"); cell(f"E{r}"); cell(f"F{r}")
            r += 1
        r += 1

    insp_block("① 입고검사", d["incoming"])
    if d.get("is_plastic"):
        sect("② 페인트 외주")
        kv("발송합", d["paint"]["sent_sum"], "회수합", d["paint"]["returned_sum"])
        r += 1
        if d.get("post_paint") and d["post_paint"].get("exists"):
            insp_block("③ 페인트후검사", d["post_paint"])

    sect("종합")
    kv("최종 양품", d.get("final_good"), "수율(%)", _rate(d.get("final_good") or 0, L.get("lot_qty", 0)))

    return _wb_bytes(wb), f"검사이력_{disp}.xlsx"


def report_excel(data=None):
    """전체 집계 엑셀. (bytes, filename) 반환."""
    import openpyxl
    from openpyxl.styles import Font

    s = summary()
    wb = openpyxl.Workbook()

    ws1 = wb.active
    ws1.title = "로트별"
    cols = ["로트번호", "입고일", "프리즘", "공급사", "로트수량", "입고양품", "입고불량", "입고불량률%", "최종양품", "수율%"]
    ws1.append(cols)
    _style_header(ws1, [f"{c}1" for c in "ABCDEFGHIJ"])
    for b in s["by_lot"]:
        ws1.append([b.get("lot_label") or b["lot_no"], b["receipt_date"], f"{b['prism_type']} {b.get('model') or ''}", b["supplier_name"],
                    b["lot_qty"], b["inc_good"], b["inc_defect"], b["inc_rate"], b["final_good"], b["yield"]])
    for col in "ABCD":
        ws1.column_dimensions[col].width = 16

    ws2 = wb.create_sheet("공급사별")
    ws2.append(["공급사", "입고수량", "검사수량", "양품", "불량", "불량률%"])
    _style_header(ws2, [f"{c}1" for c in "ABCDEF"])
    for b in s["by_supplier"]:
        ws2.append([b["supplier_name"], b["received"], b["inspected"], b["good"], b["defect"], b["defect_rate"]])

    ws3 = wb.create_sheet("항목별불량률")
    ws3.append(["검사항목", "분류", "입고불량", "입고불량률%", "페인트후불량", "페인트후불량률%"])
    _style_header(ws3, [f"{c}1" for c in "ABCDEF"])
    for b in s["by_item"]:
        ws3.append([b["name"], b["category"], b["inc_defect"], b["inc_rate"], b["post_defect"], b["post_rate"]])
    for ws in (ws2, ws3):
        ws.column_dimensions["A"].width = 18

    return _wb_bytes(wb), "프리즘_집계.xlsx"
