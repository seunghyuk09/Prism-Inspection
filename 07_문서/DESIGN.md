# Prism 검사·재고 관리 시스템 — 설계서

> Secugen Korea / 물류 · 품질. 광학 지문인식기용 Prism(Plastic/Glass)의 입고·검사·페인트·잔량 관리.
> 작성 2026-06-24. 코드 = 영어 식별자 + 한글 주석. 규칙 = 가급적 참/거짓(boolean).

## 1. 목적 / 범위
- 공급사별 입고 수량·일자, 로트 분리, **2단계 전수검사**(입고검사 → 페인트후검사), 항목별 불량/불량률, **잔량(소비) 관리**.
- 독립 웹앱으로 시작 → 추후 사내 시리얼넘버 시스템과 통합.
- 로그인 없음(웹 열면 바로 사용), 단 이력(activity_log)은 기록.

## 2. 기술 스택 (기존 입출고시스템과 동일 계열)
- 백엔드: 파이썬 표준 `http.server` (외부 의존성 0), SQLite.
- 프론트: 바닐라 HTML/CSS/JS (탭 셸).
- 실행: `00_실행센터/run_web.bat` → 포트 **10000**, 브라우저 자동 오픈.

## 3. 처리 흐름 (2단계 검사 + 소비)
```
입고(투명) → 로트분리 → 입고검사(전수) → [양품] 페인트 외주(발송/분할회수)
  → 페인트후검사(전수, 불량 점진기록) → 최종양품 → (재고)
구매계획서(월말) 임포트 → 제품별 생산수량 × 대당 소요량 → 프리즘 소비(차감) → 잔량
```

## 4. 데이터 모델 v2.2 (SQLite — 14 테이블)
| 테이블 | 역할 | 핵심 |
|--------|------|------|
| prism_master | 프리즘 종류/규격 | item_code(ERP 후입력·부분UNIQUE), prism_type(PLASTIC/GLASS), is_active |
| supplier | 공급사 | status(ACTIVE/REMNANT/STOPPED), **is_active=생성컬럼(status='ACTIVE')** |
| inspection_item | 검사항목(확장형) | applies_to_incoming/applies_to_post_paint(bool), sort_order |
| product | 제품마스터(BOM) | product_code, **prism_id(NULL=미사용)**, prism_per_unit |
| receipt | 입고 헤더 | receipt_no(UNIQUE), receipt_date, prism_id, supplier_id, received_qty |
| lot | 로트 | receipt 1:N, lot_no, lot_qty, status, UNIQUE(receipt_id,lot_no) |
| inspection | 검사 | stage(INCOMING/POST_PAINT), method(FULL/SAMPLING), is_complete, AQL컬럼, UNIQUE(lot_id,stage) |
| inspection_defect | 검사불량(롱포맷) | UNIQUE(inspection_id,item_id), defect_qty |
| paint_job | 페인트 발송 | sent_qty, is_returned |
| paint_return | 분할 회수 | paint_job 1:N, returned_qty |
| production_plan | 구매계획 헤더 | plan_month, is_final(월말최종) |
| production_plan_line | 계획 상세 | product_code, planned_qty, consumed_qty |
| consumption | 소비 원장 | prism_id, supplier_id, source(PLAN/MANUAL/ADJUST), qty |
| activity_log | 이력 | ts, category, action, target, detail(JSON), operator |

### 핵심 규칙(참/거짓 술어 — 코드에서 검증)
- `Σlot.lot_qty ≤ receipt.received_qty`
- 완료(is_complete=1)일 때만 등식 강제: `good+defect == inspected`, `defect == Σinspection_defect`, `inspected == lot_qty(전수)`. 미완료면 `≤`(soft).
- `paint_job.sent_qty ≤ incoming.good_qty`, `Σpaint_return ≤ sent_qty`, `is_returned = (Σ회수==발송)`
- `can_create_new_receipt = (supplier.status=='ACTIVE')` → REMNANT(오프렌)는 신규 입고 금지, 잔량 소진만
- `can_create_paint_job = (prism_type=='PLASTIC' AND incoming.is_complete)` → GLASS는 페인트 단계 없음
- 항목별 불량률 = `Σinspection_defect(item, stage) / inspection.inspected_qty(stage)` (단계 분리)
- 프리즘 잔량 = `Σ최종양품(prism) − Σconsumption(prism)`

### 구매계획서 임포트 포맷
- `SG-Pseudo Order ... .xlsx`, 월별 시트(예 "Jun 2026"). 헤더 5행, 데이터 7행~.
- **C열=PRODUCT(제품코드), E열=Q'ty(월 생산수량)**, F=단가, G=금액.
- 매칭: product_code → product. prism_id NULL 이면 소비 0. consumed = Q'ty × prism_per_unit.

## 5. 단계별 계획
- [x] **Phase 0 골격** — 폴더·DB(스키마+시드)·서버(포트10000)·탭 셸·대시보드. *(완료, 동작 확인)*
- [x] **Phase 1 기준정보** — 프리즘/공급사/검사항목/제품마스터 CRUD *(완료, self_check 28/0)*
- [x] **Phase 2 입고·로트** — 입고 등록 → 로트 분리(잔여 정합성·오프렌 신규입고 차단) *(완료, self_check 35/0)*
  - UI를 입출고 스타일로 정리: 다크 네이비 테마 + **2단계 메뉴(카테고리바→동적 하위메뉴)** + 홈 카테고리 카드 (NAV 설정은 `app.js` 한 곳)
- [x] **Phase 3 검사·페인트** — 입고검사 → 페인트 발송/분할회수 → 페인트후검사(점진기록) *(완료, self_check 47/0)*
  - 로트 중심 **검사·페인트 작업대**(한 화면에서 전 단계). 항목별 불량 단계 필터·실시간 불량률, is_complete 게이팅(진행중/완료), 글래스는 입고검사만
- [x] **Phase 4a 소비·잔량** — 구매계획서(.xlsx) 임포트→소비 차감, 잔량 현황(도장상태별 계산), 기초재고(오프렌 잔량) *(완료, self_check 62/0)*
  - 잔량: 유리=입고양품−소비 / 미도장=입고양품−페인트발송 / 도장완료=페인트후양품−소비. 페어(painted_into)로 페인트후→도장완료 전환 반영
- [x] **Phase 4b 집계 + 엑셀** — 입고일·로트·공급사·항목별 양품/불량/불량률·수율 + **건별(로트) 검사이력 엑셀 + 전체 집계 엑셀 다운로드** *(완료, self_check 68/0)*
- [ ] **Phase 5 (보류) 검사성적서** — 사용자 양식 확정 후 자동생성
- [x] **Phase 5 로그인/배포** — 세션 로그인(auth.py·login.html), 모든 페이지/API 게이트, 사용자관리(관리자), 기본 admin/secugen. Cloudflare Tunnel로 외부 배포 *(완료, self_check 80/0)*
- [ ] **Phase 6 (추후) 통합** — 시리얼넘버 시스템과 로그인·제품마스터 공유

## 6. 폴더 구조
```
00_설정/  00_실행센터/run_web.bat  02_DB/prism.sqlite  04_웹앱/{index.html,assets,backend/{db.py,local_server.py}}
05_도구/  07_문서/DESIGN.md  _성적서샘플/(예시 엑셀)
```
