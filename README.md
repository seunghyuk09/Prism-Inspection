# Prism 검사 · 재고 관리 (Prism-Inspection)

플라스틱/유리 프리즘의 **입고 → 입고검사 → 페인트(외주) → 페인트후검사 → 소비/잔량**을
관리하는 사내 웹앱. 파이썬 표준 라이브러리 웹서버 + 바닐라 JS 프론트, **PostgreSQL** 저장.

- 배포 주소: https://prism.secugen-logistics.com (이 PC에서 헤드리스 실행 + Cloudflare 터널)
- 저장소: https://github.com/seunghyuk09/Prism-Inspection

## 기술 스택
- 백엔드: Python `http.server`(외부 웹프레임워크 없음), `psycopg`(PostgreSQL), `openpyxl`(엑셀)
- DB: **PostgreSQL 18** (`prism` 데이터베이스, `prism` 스키마). `db.env` 없으면 SQLite 폴백(개발용)
- 프론트: HTML/CSS/JS (빌드 없음)

## 폴더
- `04_웹앱/` — 앱 본체 (`backend/` 서비스 + `assets/` 프론트 + `index.html`)
- `08_배포/` — 스키마(`schema_postgres.sql`), 이관 스크립트
- `00_설정/` — `db.env`(접속정보, git 제외) · `db.env.example`(템플릿)
- `00_실행센터/` — 실행/자동시작/감시(watchdog) 스크립트
- `02_DB/` — SQLite 폴백 파일(실데이터 아님, git 제외)

## 다른 PC에서 작업하기 (코드 개발)
GitHub가 소스의 기준입니다. 어느 PC든 아래로 clone 해서 편집 → 커밋 → 푸시하면 됩니다.

```bash
git clone https://github.com/seunghyuk09/Prism-Inspection.git
cd Prism-Inspection
pip install -r requirements.txt
```

앱을 그 PC에서 **직접 실행**하려면 DB 접속정보가 필요합니다(보안상 git에 없음):

```bash
# 00_설정/db.env 를 db.env.example 을 참고해 만든다
#   DATABASE_URL=host=<DB호스트> port=5432 dbname=prism user=postgres password=<비번>
#   PG_SCHEMA=prism
python run_server.py 10000      # http://127.0.0.1:10000
```

> `db.env` 가 없으면 앱은 빈 SQLite로 뜹니다(실데이터 아님, 기본 시드만). 실데이터로 보려면 아래 "데이터 공유" 참고.

## git 에 올라가지 않는 것(각 PC가 별도로 준비)
`.gitignore` 로 제외 — **보안/데이터**라서 의도적으로 제외합니다.
- `00_설정/db.env` — DB 접속정보(비밀번호)
- `00_설정/사용자목록.json` — 로그인 계정(비밀번호 해시)
- `02_DB/*.sqlite`, `08_배포/prism_data.sql` — 데이터 파일/덤프
- `*.log`, `__pycache__/` 등

## 데이터 공유(핵심)
**코드**는 GitHub로 어디서나 공유되지만, **데이터는 PostgreSQL 안**에 있습니다.
여러 PC가 같은 데이터를 보려면 셋 중 하나:
1. **같은 PostgreSQL 을 공유** — 모든 PC의 `db.env` 를 하나의 DB 서버로 향하게 함(네트워크 접근 가능한 PG 또는 클라우드 PG). *가장 확실한 "어디서나 작업".*
2. **배포 웹사이트 사용** — 단순히 앱을 *쓰기만* 하면 https://prism.secugen-logistics.com 로 어느 PC에서든 접속(이미 이 PC에서 24시간 실행 중).
3. **각 PC 로컬 PG** — 데이터는 공유 안 됨(개발/테스트용).

## 이 PC에서 실행/자동시작
- 실행: `00_실행센터/start_hidden.vbs`(창 없이 서버+터널) — 로그온 시 자동시작 등록됨
- 감시: `00_실행센터/watchdog_loop.vbs`(2분마다 죽으면 자동 재시작)
- DB: PostgreSQL 서비스(`postgresql-x64-18`), 포트 5432
