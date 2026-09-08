# 리눅스 배포 (systemd)

윈도우의 `.vbs` 자동시작 + watchdog 을 리눅스 표준 방식(systemd)으로 대체한다.
**WSL · Hyper-V VM · 클라우드 VPS 어디서든 같은 방식으로 동작한다.**

## 설계 원칙 (지킬 것)

- **하드코딩 금지** — 프로젝트 경로·실행 사용자·파이썬 위치는 `install.sh` 가 자동 감지한다.
  특정 PC 전용 경로를 파일에 적지 않는다.
- **기계별 차이는 설정으로** — 포트·백업 위치 등은 `/etc/prism/prism.env` 에만 둔다.
  앱 코드는 어느 기계에서든 동일하다.
- **앱 코드는 건드리지 않는다** — 배포 계층만 추가한다.

## 설치

```bash
sudo bash 08_배포/linux/install.sh
sudo systemctl start prism
systemctl status prism --no-pager
```

## 구성

| 파일 | 역할 |
|---|---|
| `install.sh` | 환경 감지 → systemd 유닛 생성·등록 (재실행 안전) |
| `backup_db.sh` | `pg_dump` 백업 + 보관기간 지난 파일 정리 |
| `/etc/prism/prism.env` | **기계별 설정** (포트·DB명·백업 경로·보관일). 설치 시 없으면 생성, 있으면 유지 |
| `prism.service` | 웹서버 — 부팅 시 자동시작, 죽으면 자동재시작(`Restart=always`) |
| `prism-backup.timer` | 매일 03:30 DB 백업 |

## 자주 쓰는 명령

```bash
sudo systemctl start|stop|restart prism   # 시작 / 정지 / 재시작
systemctl status prism --no-pager         # 상태 확인
journalctl -u prism -n 50 --no-pager      # 서비스 로그
tail -n 50 logs/server.log                # 앱 로그
sudo systemctl start prism-backup         # 백업 즉시 1회
systemctl list-timers prism-backup        # 다음 백업 예정 시각
```

## DB 접속 설정

앱의 DB 접속은 `00_설정/db.env` 가 결정한다(이 파일은 git 에 올리지 않는다).

```
DATABASE_URL=dbname=prism      # 유닉스 소켓 + peer 인증 (비밀번호 불필요)
PG_SCHEMA=prism
```

`DATABASE_URL` 이 없으면 자동으로 SQLite 로 동작한다. 즉 **설정 한 줄로 DB 백엔드가 바뀌며,
앱 코드는 수정하지 않는다.**

## 다른 서버로 옮길 때

1. 코드 가져오기 (`git clone` 또는 복사)
2. `sudo apt install -y postgresql python3-psycopg python3-openpyxl`
3. DB 생성 + 덤프 복원
4. `00_설정/db.env` 작성
5. `sudo bash 08_배포/linux/install.sh && sudo systemctl start prism`

경로가 달라도 `install.sh` 가 알아서 감지하므로 **수정할 것이 없다.**
