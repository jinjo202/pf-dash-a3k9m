# AGENTS.md — 이 저장소에서 일하는 모든 코딩 에이전트를 위한 지침

> 이 파일이 저장소 전체 지침의 **단일 소스 오브 트루스**다. `CLAUDE.md`는 핵심 안전규칙 + 이 파일로의 포인터다.
> 한국어로 소통한다(사용자 선호: 간결·직설). 사용자는 기관 포트폴리오 매니저로 정확한 회계수치를 중시한다.

---

## 0. 이 폴더의 정체성 — ⚠️ 한 repo에 여러 프로젝트가 섞여 있다

이 디렉터리(`C:\Users\ocarr\Developer\dividends`, repo `jinjo202/pf-dash-a3k9m`, **public**)는 하나의 git 저장소이지만 **성격과 방향이 다른 작업들이 한데 섞여 있다.** 작업을 시작하기 전에 지금 다루는 파일이 아래 어느 프로젝트에 속하는지 먼저 분류하라. 프로젝트마다 규칙·배포·민감도가 다르다.

| # | 프로젝트 | 무엇 | git 상태 | 자동화 |
|---|---|---|---|---|
| **P1** | **포트폴리오·시황 대시보드** (메인) | 정적 HTML 대시보드 + Python 데이터 파이프라인 | committed | cron 하루 8회 |
| **P2** | **KIND 배당공시 모니터링** | 거래소 공시 폴링 → 메일 발송 (PowerShell/SMTP) | **gitignored** | (미완) cron 예정 |
| **P3** | **로컬 유틸 / 개발 도구** | 서버·실행·검증 스크립트 | 혼재 | 수동 |

핵심: **P2는 P1과 무관한 별개 기능이고 gitignore되어 있다.** P1 작업 중에 P2 파일(`config.json`, `fetch_disclosures.ps1`, `state.json`, `pending.json`, `monitor.log`)을 건드리거나 commit하지 마라.

---

## 1. 🔴 절대 규칙 (모든 프로젝트 공통, 위반 시 데이터 손실)

1. **작업 전 항상 동기화**: `git status` → `git fetch origin main` → `git pull --ff-only origin main`. cron이 하루 8회 push하므로 origin이 수시로 앞선다.
2. **절대 금지**:
   - `git push --force` / `--force-with-lease` (cron 데이터 손실 위험)
   - 평문 `portfolio-data.plain.js` commit
   - `.password` commit
   - 자동 데이터 파일 직접 편집 — **항상 source script 경유** (`update_prices.py`, `fetch_*.py`, `_apply_real_returns.py` 등)
3. **데이터 파일 충돌 시 원격 우선**: `git checkout origin/main -- <파일>` (또는 `--theirs`).
4. **commit/push는 사용자가 요청할 때만.** 커밋 메시지 끝에:
   `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
5. **public repo**: holdings 실내용·자격증명·평문 데이터를 절대 노출하지 마라. 민감 메모는 `_ref/`(gitignored)에만.
6. **검증은 브라우저와 동일하게**: 암호화 데이터 검증은 Python이 아니라 **Node Web Crypto**로(Python `json.loads`는 `NaN`을 통과시키지만 브라우저 `JSON.parse`는 거부 — 이 불일치가 과거 로그인 불가 버그의 원인).

---

## 2. P1 — 포트폴리오·시황 대시보드 (메인 프로젝트)

GitHub Pages 정적 호스팅. 라이브 `https://jinjo202.github.io/pf-dash-a3k9m/`. 절대수익 지향 기관 포트폴리오(~5,250억, 28종목) 관점.

P1은 다시 **6개의 독립적 하위 모듈**로 나뉜다. 각 모듈은 자기 HTML 페이지 + 자기 데이터 파일 + 자기 fetch 스크립트를 가진다.

### 2.1 모듈 지도

| 모듈 | 프런트엔드 | 데이터 파일 | 생성 스크립트 |
|---|---|---|---|
| **포트폴리오** | `portfolio.html` | `portfolio-data.js`(암호화) | `update_prices.py`, `compute_historical.py`, `_apply_real_returns.py` |
| **매크로/레짐** | `macro.html` | `macro-data.js`, `country-model.js`, `country-model-state.json` | `fetch_macro.py`, `weekly/country_model.py` |
| **데일리 시황** | `daily.html` | `daily-data.js`, `benchmarks.js`, `holding-news.js`, `constituent-news.js`, `kr_flows.json`, `kr_deposit.json` | `fetch_daily.py`, `fetch_benchmarks.py`, `fetch_kr_flows.py`, `fetch_kr_deposit.py`, `fetch_constituent_news.py`, `fetch_sector_news.py` |
| **펀드매니저** | `fm.html` | `fm-data.js`(수동 큐레이션), `fm-financials.js` | `fetch_fm_financials.py` |
| **브리핑(시황메일)** | (`daily.html` 내 표시) | `briefing-data.js`, `briefings-archive.js`, `briefings-archive-asia.js`, `briefings/{date}.md` | `briefing/generate_briefing.py`, `briefing/send_email_{us,asia}.py` |
| **주간회의자료** | (xlsx 산출물 + `weekly-data.js`) | `weekly-data.js`, `weekly/enrich.json` | `weekly/weekly_report.py`, `weekly/fetch_sentiment.py` |

지원 fetch 스크립트: `fetch_valuations.py`, `fetch_historical_valuations.py`, `fetch_etf_holdings.py`, `fetch_underlying_returns.py`, `compute_corr_vol.py`.

### 2.2 암호화 데이터 흐름 (포트폴리오)

```
portfolio-data.plain.js  (평문, gitignored, 로컬 작업용)
        ⇅  encrypt_data.py decrypt|encrypt   (AES-GCM, 비번은 .password/env)
portfolio-data.js        (암호화본, committed)
```
- 비번: **`.password` 파일 또는 `PORTFOLIO_PASSWORD` env var에만 보관**(소스·문서에 평문 금지 — public repo). BOM 없이 저장.
- `encrypt_data.py`는 암호화 직전 `NaN/Infinity → null` 정화 + `allow_nan=False`.
- 거래 추가/snapshot 적용은 `_apply_real_returns.py`(gitignored, 로컬 전용). xlsx 원본이 잠겨있으면 **surgical 직접 편집 패턴** 사용(핸드오프 인덱스 §2 참조).

### 2.3 표준 작업 시퀀스 (데이터 변경 시)

```bash
# 1. 동기화 (필수)
git fetch origin main && git pull --ff-only origin main

# 2. 데이터 작업이면: 복호화 → 편집 → 재암호화
python encrypt_data.py decrypt
#   ... 편집 (스크립트 경유) ...
python update_prices.py          # 가격
python compute_historical.py     # historical 시계열 (필요시)
python encrypt_data.py encrypt

# 3. portfolio.html 변경 시 CODE_VERSION 한 단계 올림 (캐시버스팅)
# 4. cron 경합 재확인 후 commit/push
git fetch origin main; git log HEAD..origin/main --oneline   # 비어야 안전
git add <파일>; git commit -m "..."; git push
```

Push 충돌 시(작업 중 cron이 push): `git fetch` → `git reset --soft origin/main` → 재 `git add` → 재 commit → push. (daily-update.yml과 동일 패턴.)

### 2.4 "최신으로 업데이트" 요청 = 풀 사이클

사용자가 "배포해줘 / 반영해줘 / 최신으로 업데이트"라고 하면 편집→암호화→push→Pages 검증까지 기대한다. 로컬 FRED throttle 때문에 **매크로/최고품질 데이터 갱신은 항상 GitHub 워크플로 경로**:
```bash
gh workflow run daily-update.yml --ref main
gh run watch <id> --exit-status --interval 20
```

---

## 3. P2 — KIND 배당공시 모니터링 (별개 프로젝트, gitignored)

거래소 KIND 공시에서 특정 종목의 "현금·현물 배당 결정" 공시를 폴링해 두 메일로 발송하는 **독립 PowerShell/SMTP 도구.** P1 대시보드와 코드·데이터를 공유하지 않는다.

- 파일(모두 gitignored): `config.json`(타겟 8종·필터), `state.json`(중복발송 방지), `pending.json`, `fetch_disclosures.ps1`(KIND 스크랩, 검증됨), `monitor.log`.
- 발송: PowerShell `Send-MailMessage` + Gmail SMTP (Outlook COM·Gmail MCP는 배제됨).
- **상태**: Gmail 앱비번 발급 대기에서 멈춤(`send_mail.ps1`·cron 미완). 상세는 `_ref/SESSION_HANDOFF_kind-disclosure_2026-05-17.md`.
- ⚠️ ps1 인코딩: PowerShell 5.1은 ANSI(CP949)로 읽음 → 한글 상수는 `.ps1`에 박지 말고 **별도 UTF-8 JSON**으로.

---

## 4. P3 — 로컬 유틸 / 개발 도구

| 파일 | 역할 | git |
|---|---|---|
| `serve.py` | 로컬 HTTP 서버 + `/fm-chat`(구독차감 채팅, fail-closed 과금차단) | committed |
| `daily_run.ps1`, `setup_daily_task.ps1`, `setup_server.ps1` | 로컬 실행/스케줄 헬퍼 | committed |
| `_apply_real_returns.py`, `_fifo_check.py`, `_read_full.py` | 데이터 재빌드/검증 헬퍼 | **gitignored** (`_*.py`) |
| `verify_indices.py` | 지수 데이터 교차검증 | committed |
| `design-mockups.html` | 디자인 목업 | committed |

로컬 미리보기: `python serve.py` → `http://localhost:8000/portfolio.html` (게이트 비번은 `.password` 참조). 정적만이면 preview 툴 포트 8731.

---

## 5. 반복되는 함정 (전 세션 공통)

1. **cp949 mojibake**: Windows 터미널 한글 깨짐 → 종목명-값 매칭 시 `PYTHONIOENCODING=utf-8` 강제 또는 ticker로 대조.
2. **Python이 NaN을 숨김**: 데이터 검증은 Node Web Crypto로(§1.6).
3. **FRED 로컬 throttle**: 이 PC IP는 FRED 시계열에서 막힘 → "최신 갱신"은 `gh workflow run`(GitHub은 정상).
4. **병렬 세션 충돌**: 같은 디렉터리에서 다른 에이전트 세션이 동시 작업할 수 있음 → 시작 시 `git status` 확인, 편집 즉시 단일 커밋으로 분리.
5. **cron 경합**: 작업 중 cron이 push 가능 → commit 직전 `git fetch`로 재확인.
6. **2026 타임라인**: 이 환경은 2026.6 시점. 학습지식(컷오프 이전)으로 시세를 "오류"로 판단하지 말고 실제 소스(네이버/FnGuide/yfinance)로 교차검증. (예: 삼성전자 ₩322,500은 정상값.)
7. **weekly_report 템플릿 누적**: 직전 산출물을 템플릿으로 써서 블록이 누적됨 → `_clear_appended_blocks()`로 정리, 회의 당일엔 `--meeting` 명시.

---

## 6. 자동화 워크플로 (`.github/workflows/`)

- `daily-update.yml` — cron 하루 8회(한국장 06:37~07:29 UTC, 미국장 21:41~23:47 UTC) + `workflow_dispatch` + `repository_dispatch(daily-trigger)`. concurrency lock으로 직렬화. `git reset --hard origin/main` 후 TRACKED 데이터파일만 덮어쓰고 커밋(소스파일 보호), 5회 재시도.
- `briefing-us.yml` (08:00·08:40·09:30 KST) / `briefing-asia.yml` (15:50·16:20·17:00 KST) — `generate_briefing.py --skip-if-exists` + SMTP 발송. **`ANTHROPIC_API_KEY` secret 필요**.
- secrets: `ANTHROPIC_API_KEY`, `GMAIL_SENDER`, `GMAIL_APP_PASSWORD`, `PORTFOLIO_PASSWORD`. 변수 `ANTHROPIC_MODEL=claude-sonnet-4-5`(브리핑 생성, 비용절감용).

---

## 7. 📌 핸드오프 인덱스를 참고할 때

`_ref/` 폴더(gitignored)에 과거 세션의 상세 핸드오프 문서들과 **`_HANDOFF_INDEX.md`(인덱스)** 가 있다. 이 AGENTS.md는 "구조와 규칙"을, 핸드오프는 "특정 작업의 깊은 맥락·버그 히스토리·자격증명"을 담는다.

**다음 상황에서 `_ref/_HANDOFF_INDEX.md`를 먼저 읽고, 거기서 가리키는 개별 핸드오프로 들어가라:**
- 포트폴리오 **회계 모델**(book_basis/cost_sold/realized/avg_invested, 수익률 정의) 또는 매매 surgical 반영이 필요할 때 → `SESSION_HANDOFF_2026-06-18.md`
- **브리핑/주간자료** 생성·게시 플로우의 세부가 필요할 때 → `session-handoff-2026-06-18.md`
- **매크로/EPS/레짐** 데이터 소스·갱신 절차가 필요할 때 → `SESSION_HANDOFF_pfdash_2026-06_old.md`
- **펀드매니저 탭/구독차감 채팅** 빌링 메커니즘이 필요할 때 → `SESSION-HANDOFF-2026-06-16_old.md`
- **KIND 공시(P2)** 작업을 이어갈 때 → `SESSION_HANDOFF_kind-disclosure_2026-05-17.md`
- 펜딩 작업·자격증명(cron-job.org PAT, xlsx 경로)이 필요할 때 → 인덱스 §4 / 각 핸드오프 §1

인덱스를 통해 가되, 인덱스가 가리키는 사실이 코드와 어긋나면 **코드를 신뢰**하라(핸드오프는 작성 시점 스냅샷이다).

---

## 8. 환경 / 사용자 컨텍스트

- OS: Windows 11, PowerShell 5.1(주) + Bash 사용 가능. 한글 출력 cp949 주의.
- Python deps: `requirements.txt` (yfinance, pandas, numpy, cryptography, deep-translator).
- 사용자 메일: jklee@benow.co.kr. 한국어·간결·직설 선호. 브로커 FIFO 매각이익을 자주 정정해주므로 회계수치는 그 값을 신뢰.
- gstack 브라우즈는 이 PC에서 Application Control 정책에 막힐 수 있음 → Node fetch + Web Crypto로 라이브 검증.
