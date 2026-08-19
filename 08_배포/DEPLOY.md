# 배포 가이드 (GitHub · PostgreSQL · 서버/DNS)

> 이 앱은 **Python 표준 http.server + SQLite** 로 동작합니다(외부 의존성 0).
> 아래는 (1) GitHub 업로드, (2) PostgreSQL 로 데이터 이관, (3) 서버/도메인 배포 절차입니다.
> **비밀번호·토큰은 각 담당자(본인)가 직접 입력**합니다.

---

## 1) GitHub 업로드

로컬 저장소는 이미 초기화 + 최초 커밋 완료(민감파일 제외). 남은 건 원격 연결 + 푸시.

**방법 A — GitHub CLI(gh) 설치 후 (권장):**
```bash
winget install --id GitHub.cli        # gh 설치
gh auth login                          # 브라우저로 본인 계정 인증
gh repo create secugen-prism --private --source . --remote origin --push
```

**방법 B — github.com 에서 빈 저장소(Private) 먼저 만들고:**
```bash
git remote add origin https://github.com/<계정>/<저장소>.git
git branch -M main
git push -u origin main                # 최초 1회는 본인 계정 인증창이 뜸
```

> ⚠️ DB 실데이터(`*.sqlite`)와 비밀번호 해시(`00_설정/사용자목록.json`)는 `.gitignore` 로
> **일부러 제외**됩니다. 데이터는 GitHub 가 아니라 아래 PostgreSQL 로 이관하세요.

---

## 2) PostgreSQL 로 데이터 이관 ("새 섹터" = `prism` 스키마)

기존 PG 인스턴스 안에 격리된 스키마 `prism` 을 만들어 올립니다.

```bash
# (1) 최신 데이터 덤프 생성 (드라이버 불필요)
python 08_배포/sqlite_to_pg.py          # -> 08_배포/prism_data.sql

# (2) 스키마 + 데이터 적재  (<conn> = postgresql://USER:PW@HOST:PORT/DBNAME)
psql "<conn>" -f 08_배포/schema_postgres.sql
psql "<conn>" -f 08_배포/prism_data.sql

# (3) 검증
psql "<conn>" -c "SET search_path TO prism; SELECT count(*) FROM receipt;"     # 9
psql "<conn>" -c "SET search_path TO prism; SELECT count(*) FROM inspection;"  # 8
```

> 접속정보(비밀번호 포함)는 저장소에 커밋하지 마세요. `PGPASSWORD` 환경변수나
> `~/.pgpass` 를 쓰면 명령에 비밀번호를 노출하지 않아도 됩니다.

### 앱을 PostgreSQL 로 돌리기 (✅ 포팅 완료 — 듀얼 지원)
`db.py` 가 **환경변수 `DATABASE_URL`** 로 백엔드를 고릅니다. 서비스 코드는 그대로.
```bash
pip install "psycopg[binary]"                       # PG 드라이버(서버에 설치)
export DATABASE_URL="postgresql://USER:PW@HOST:PORT/DBNAME"   # 있으면 PG, 없으면 SQLite
export PG_SCHEMA="prism"                             # (선택) 기본 prism
python run_server.py 10000
```
- 연결 래퍼가 `?`→`%s`, `INSERT OR IGNORE`→`ON CONFLICT`, `lastrowid`→`RETURNING`,
  UniqueViolation→sqlite IntegrityError 를 자동 흡수 → **서비스 15개 무변경**.
- `DATABASE_URL` 을 **안 주면 기존 SQLite** 그대로(개발/롤백 안전). SQLite 회귀검증 90/0 통과.
- ⚠️ **PG 런타임 최종검증은 실제 PG 연결 후**(이 개발환경엔 PG 서버 없음) — 배포 시 함께 확인.

---

## 3) 서버 / 도메인 / DNS

현재 상태: **로컬 PC + Cloudflare Tunnel** 로 `https://prism.secugen-logistics.com` 이미 서비스 중.

**옵션 A — 지금 방식 유지(로컬 + 터널):** 추가 작업 거의 없음. 새 서브도메인만 원하면:
```bash
cloudflared tunnel route dns <터널이름> <새서브도메인>.secugen-logistics.com
# config.yml ingress 에 해당 호스트 -> http://localhost:10000 추가
```

**옵션 B — 상시 가동 클라우드 서버(VPS)로 이전:** 리눅스 서버 준비 후
`python run_server.py 10000` 를 서비스(systemd)로 등록 + 그 서버에서 cloudflared 실행.
(서버 provisioning·SSH·DNS 는 본인 클라우드/Cloudflare 계정 필요)

**새 도메인(예: SecuGen-Prism-archive.com):** 도메인 등록 + Cloudflare 존 추가(본인 계정)
후, 위와 동일하게 터널 라우팅.
