# 매크로 대시보드 전용 로컬 자동 갱신 (Windows 작업 스케줄러용)
# investing.com(VKOSPI 등)이 GitHub Actions IP는 막지만 이 PC 로컬 IP는 통과시켜서,
# 로컬 실행이 유일한 갱신 경로인 지표(VKOSPI 등)를 하루 2회 살려주는 용도.
# macro-data.js 외 다른 파일(portfolio-data.js 등)은 절대 건드리지 않음.
#
# 주의(PowerShell 5.1):
#  - 이 파일은 반드시 UTF-8 BOM으로 저장. BOM 없으면 cp949로 읽혀 한글 깨지고 파싱 실패.
#  - git 등 네이티브 exe에 `2>&1` 쓰지 말 것. stderr가 ErrorRecord로 승격돼
#    $ErrorActionPreference="Stop"과 만나면 정상 출력에도 스크립트가 죽음.
#    성공 여부는 $LASTEXITCODE로만 판정.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$logFile = Join-Path $here "macro_daily_run.log"
function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding utf8
}

function Git-Run($argList, $what) {
    # 네이티브 호출은 예외를 안 던지므로 exit code로만 판정
    & git @argList | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "$what 실패 (exit $LASTEXITCODE)" }
}

Log "=== macro_daily_run 시작 ==="

try {
    # 1) 동기화 (cron이 하루 8회 push하므로 항상 최신에서 시작)
    # pull 실패는 치명적이지 않다 — 이 작업 폴더는 병렬 세션과 공유돼 미커밋 변경이 있으면
    # --ff-only가 거부한다. 그 경우에도 아래 push 재시도(fetch→reset --soft→재커밋)가
    # 낡은 베이스를 알아서 정리하므로, 여기서 중단하지 말고 경고만 남기고 진행.
    Git-Run @("fetch", "origin", "main") "git fetch"
    & git pull --ff-only origin main | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Log "경고: git pull --ff-only 스킵 (미커밋 변경/분기 추정) — push 단계에서 재정렬 시도"
    }

    # 2) 매크로 데이터 갱신 (FRED_API_KEY는 영구 User 환경변수)
    & python fetch_macro.py
    if ($LASTEXITCODE -ne 0) { throw "fetch_macro.py 실패 (exit $LASTEXITCODE)" }

    # 3) macro-data.js 변경분만 커밋 (다른 파일 절대 add 안 함)
    Git-Run @("add", "macro-data.js") "git add"
    $staged = & git diff --cached --name-only
    if (-not $staged) {
        Log "변경 없음 — 커밋 생략"
        Log "=== 종료 (성공) ==="
        exit 0
    }

    $msg = "auto: macro-data 로컬 갱신 (VKOSPI/ISM/AAII 등) {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm")
    Git-Run @("commit", "-m", $msg) "git commit"

    # 4) push (cron 경합 시 최대 3회: fetch → reset --soft → 재커밋 → push)
    $pushed = $false
    for ($i = 1; $i -le 3; $i++) {
        & git push | Out-Null
        if ($LASTEXITCODE -eq 0) { $pushed = $true; break }
        Log "push 실패($i/3) — cron 경합 가능성, reset --soft 후 재시도"
        Git-Run @("fetch", "origin", "main") "git fetch(재시도)"
        Git-Run @("reset", "--soft", "origin/main") "git reset --soft"
        Git-Run @("add", "macro-data.js") "git add(재시도)"
        & git commit -m $msg | Out-Null
    }
    if (-not $pushed) { throw "push 3회 재시도 후에도 실패" }

    Log "macro-data.js 갱신·푸시 완료"
    Log "=== 종료 (성공) ==="
} catch {
    Log "오류: $_"
    Log "=== 종료 (실패) ==="
    exit 1
}
