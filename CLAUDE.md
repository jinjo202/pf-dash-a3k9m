# pf-dash-a3k9m — Claude 작업 규칙

## ⚠️ 모든 작업 시작 전 필수: 최신 main 동기화

이 repo는 GitHub Actions cron이 **하루 8번** (한국장 마감 직후 4번, 미국장 마감 후 4번) 자동으로 데이터를 갱신해서 push해. 어떤 작업이든 시작하기 전에 반드시:

```bash
git status                          # 1. 깨끗한지 확인
git fetch origin main               # 2. 원격 상태 가져오기
git pull --ff-only origin main      # 3. fast-forward로 동기화
```

**fast-forward 불가**(로컬에 commit이 있는데 원격이 앞서 있음) 시:
1. 로컬 변경사항을 `git stash` 로 일시 보관
2. `git pull --ff-only` 로 동기화
3. `git stash pop` 으로 복원
4. 충돌 발생 시 데이터 파일(`portfolio-data.js`, `prices_log.json`, `benchmarks.js`)은 **항상 원격 우선**(`git checkout --theirs <파일>`) — 그 다음 필요하면 스크립트 재실행

자동 데이터 파일을 직접 편집하지 마. 항상 source script(`update_prices.py`, `_apply_real_returns.py`, `fetch_*.py` 등)를 통해서.

## 파일 구조 요약

- `portfolio-data.plain.js` — 평문 (gitignored, 로컬 작업용)
- `portfolio-data.js` — 암호화본 (committed). `encrypt_data.py` 로 평문↔암호 변환
- `_apply_real_returns.py` — 매매내역/xlsx snapshot 적용. **gitignored**. 거래 추가/수정 시 사용
- `update_prices.py` — yfinance에서 일일 가격 받아 mkt 갱신
- `compute_historical.py` — historical YTD 시리즈 생성
- `fetch_benchmarks.py` — 벤치마크 지수 (KOSPI, S&P, VIX, KR 10Y 등)
- `.password` — 암호화 키 (gitignored). UTF-8 BOM 없이 저장 (encrypt_data.py가 BOM 자동 제거하지만 안전을 위해)

## 비밀번호

`ssfire`. `.password` 파일 또는 `PORTFOLIO_PASSWORD` env var.

## 표준 작업 sequence (거래 추가/snapshot 갱신 후)

```bash
# 1. 동기화 (필수)
git pull --ff-only origin main

# 2. 평문 복호화 (작업 시작 전)
python encrypt_data.py decrypt

# 3. _apply_real_returns.py 등으로 데이터 수정
python _apply_real_returns.py
python update_prices.py
python compute_historical.py     # historical 시리즈도 필요하면

# 4. 재암호화
python encrypt_data.py encrypt

# 5. 다시 한번 fast-forward 시도 (긴 작업 동안 cron이 push했을 수 있음)
git fetch origin main
git log HEAD..origin/main --oneline | head

# 만약 원격이 앞섰다면:
# - 우리 변경(portfolio-data.js)을 stash
# - git pull --ff-only
# - 재암호화 (왜냐하면 원격의 portfolio-data.js를 기반으로 복호화/재처리 필요)
# - commit + push

# 6. 정상 case
git add portfolio-data.js
git commit -m "..."
git push
```

## Push 충돌 처리

원격이 작업 중에 변했고 push 실패 시:

```bash
git fetch origin main
git reset --soft origin/main      # 우리 commit 취소, 변경사항은 staged 유지
git add portfolio-data.js          # 다시 add
git commit -m "..."                # origin/main 위에 새 commit
git push
```

이게 daily-update.yml workflow가 쓰는 패턴과 동일.

## ❌ 절대 하지 말 것

- `git push --force` / `git push --force-with-lease` (cron 데이터 손실 위험)
- 평문 `portfolio-data.plain.js` commit
- `.password` 파일 commit (gitignored 확인)
- 자동 데이터 파일 (`portfolio-data.js`, `prices_log.json`, `benchmarks.js`) 직접 편집

## 자동 워크플로우 (참고)

`.github/workflows/daily-update.yml`:
- 한국장 마감: 06:37, 06:53, 07:11, 07:29 UTC (= 15:37~16:29 KST)
- 미국장 마감: 21:41, 22:07, 22:29, 23:47 UTC (= 06:41~08:47 KST 다음날)
- 동시 실행은 concurrency lock으로 직렬화
- Push 실패 시 `git reset --soft origin/main` 후 재커밋 패턴으로 5회 재시도
