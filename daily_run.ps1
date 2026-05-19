# 매일 1회 실행: 가격 갱신 → 암호화 → Git push (Pages 자동 재배포)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$ts] daily_run 시작"

# 1) 복호화 (현재 portfolio-data.js → portfolio-data.plain.js)
python encrypt_data.py decrypt
if ($LASTEXITCODE -ne 0) { throw "decrypt 실패" }

# 2) 가격 갱신 (plain 파일을 in-place 갱신)
python update_prices.py
if ($LASTEXITCODE -ne 0) { throw "update_prices 실패" }

# 2b) 상관 반영 변동성 재계산 (주중에만 의미 있음 — 실패해도 전체는 진행)
python compute_corr_vol.py
if ($LASTEXITCODE -ne 0) { Write-Warning "compute_corr_vol 실패 — 변동성 표는 직전 값 유지" }

# 2c) 시장 지수 (KOSPI/KOSDAQ/S&P/NASDAQ/SOX/USDKRW) YTD 갱신
python fetch_benchmarks.py
if ($LASTEXITCODE -ne 0) { Write-Warning "fetch_benchmarks 실패 — 지수 띠는 직전 값 유지" }

# 2d) Historical YTD 시리즈 (포트폴리오 vs ACWI 백테스트 + 스냅샷용)
python compute_historical.py
if ($LASTEXITCODE -ne 0) { Write-Warning "compute_historical 실패 — 백테스트는 직전 값 유지" }

# 2e) ETF 상위 5 구성종목 (yfinance funds_data) — 주 1~2회면 충분하나 매일 시도
python fetch_etf_holdings.py
if ($LASTEXITCODE -ne 0) { Write-Warning "fetch_etf_holdings 실패 — 직전 값 유지" }

# 2f) Underlying 종목별 YTD 수익률 (알파 분해 펼침 행용)
python fetch_underlying_returns.py
if ($LASTEXITCODE -ne 0) { Write-Warning "fetch_underlying_returns 실패 — 직전 값 유지" }

# 2g) PER/PBR/ROE (밸류에이션) — 주 1~2회면 충분하나 매일 시도
python fetch_valuations.py
if ($LASTEXITCODE -ne 0) { Write-Warning "fetch_valuations 실패 — 직전 값 유지" }

# 3) 재암호화 (plain → portfolio-data.js)
python encrypt_data.py encrypt
if ($LASTEXITCODE -ne 0) { throw "encrypt 실패" }

# 4) 변경분 push
git add portfolio-data.js prices_log.json benchmarks.js
$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host "변경 없음."
    exit 0
}
git commit -m "Daily price update ($(Get-Date -Format 'yyyy-MM-dd'))"
git push
Write-Host "[$ts] push 완료"
