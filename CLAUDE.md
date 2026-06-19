# CLAUDE.md — pf-dash-a3k9m

> **전체 지침은 [AGENTS.md](AGENTS.md)가 단일 소스 오브 트루스다.** 작업 시작 전 AGENTS.md를 읽어라.
> 이 파일은 가장 중요한 안전규칙만 추려 빠르게 상기시키는 용도다.
> 한국어로 소통한다(사용자 선호: 간결·직설).

---

## ⚠️ 이 폴더엔 여러 프로젝트가 섞여 있다

하나의 git repo지만 성격이 다른 작업이 공존한다. 작업 전 지금 파일이 어디 속하는지 분류하라:

- **P1 포트폴리오·시황 대시보드** (메인, committed, cron 하루 8회) — `portfolio/macro/daily/fm.html` + 데이터 파이프라인
- **P2 KIND 배당공시 모니터링** (별개, gitignored, PowerShell/SMTP) — `config.json`·`fetch_disclosures.ps1`·`state.json` 등. **P1 작업 중 건드리지 말 것**
- **P3 로컬 유틸** — `serve.py`·`*.ps1`·`_*.py`

→ 모듈 지도·데이터 흐름·작업 시퀀스 전체는 **AGENTS.md** 참조.

---

## 🔴 절대 규칙 (위반 시 데이터 손실)

1. **작업 전 동기화 필수**: `git status` → `git fetch origin main` → `git pull --ff-only origin main`. cron이 하루 8회 push한다.
   - fast-forward 불가 시: `git stash` → `git pull --ff-only` → `git stash pop`. 데이터 파일 충돌은 **원격 우선**(`git checkout origin/main -- <파일>`).
2. **절대 금지**:
   - `git push --force` / `--force-with-lease` (cron 데이터 손실)
   - 평문 `portfolio-data.plain.js` commit
   - `.password` commit
   - 자동 데이터 파일(`portfolio-data.js`, `prices_log.json`, `benchmarks.js`, `macro-data.js`, `daily-data.js`, `kr_*.json` 등) 직접 편집 → **항상 source script 경유**
3. **commit/push는 사용자가 요청할 때만.** 메시지 끝: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
4. **public repo**: holdings 실내용·평문 데이터 노출 금지. 민감 메모는 `_ref/`(gitignored)에만.
5. **검증은 Node Web Crypto로** (Python `json.loads`는 NaN을 통과시켜 버그를 숨긴다).

## 비밀번호

포트폴리오 게이트 비번은 **`.password` 파일 또는 `PORTFOLIO_PASSWORD` env var에만 보관한다**(소스·문서에 평문 금지 — public repo). 암복호화: `python encrypt_data.py decrypt|encrypt`.

## 표준 작업 시퀀스 (데이터 변경 시)

```bash
git fetch origin main && git pull --ff-only origin main   # 1. 동기화
python encrypt_data.py decrypt                             # 2. 복호화
#   ... 스크립트로 데이터 수정 (update_prices.py / _apply_real_returns.py / fetch_*.py) ...
python encrypt_data.py encrypt                             # 3. 재암호화
git fetch origin main; git log HEAD..origin/main --oneline # 4. cron 경합 재확인 (비어야 안전)
git add <파일>; git commit -m "..."; git push              # 5. 커밋
```
Push 충돌 시: `git fetch` → `git reset --soft origin/main` → 재 add → 재 commit → push (daily-update.yml과 동일 패턴).

## 📌 핸드오프 인덱스 참고

특정 작업의 깊은 맥락(회계 모델, 버그 히스토리, 브리핑/매크로/펀드매니저 세부, 자격증명, 펜딩 작업)이 필요하면 **`_ref/_HANDOFF_INDEX.md`** 를 먼저 읽고 거기서 가리키는 개별 핸드오프 문서로 들어가라. 어떤 상황에 어느 문서를 볼지는 AGENTS.md §7에 정리돼 있다. 핸드오프와 코드가 어긋나면 **코드를 신뢰**하라.

---
_세부 사항·모듈 지도·반복 함정·워크플로 전체는 [AGENTS.md](AGENTS.md)에 있다._
