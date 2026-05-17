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

# 3) 재암호화 (plain → portfolio-data.js)
python encrypt_data.py encrypt
if ($LASTEXITCODE -ne 0) { throw "encrypt 실패" }

# 4) 변경분 push
git add portfolio-data.js prices_log.json
$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host "변경 없음."
    exit 0
}
git commit -m "Daily price update ($(Get-Date -Format 'yyyy-MM-dd'))"
git push
Write-Host "[$ts] push 완료"
