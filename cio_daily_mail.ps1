# CIO 데일리 의견 생성 + 메일 발송 (Windows 작업 스케줄러용)
#
# 생성은 로컬 Claude Code CLI(구독 차감)로 돈다 — ANTHROPIC_API_KEY 등 과금 env는
# generate_briefing._call_claude_cli 가 제거하므로 종량제로 새지 않는다.
# CI(fm-cio.yml)도 같은 스크립트를 하루 2회 돌리지만, 그건 대시보드용 파일 갱신이고
# 메일은 이 로컬 작업만 보낸다(중복 방지는 --skip-if-sent 가 as_of+slot 로 판정).
#
# 주의(PowerShell 5.1) — macro_daily_run.ps1 과 동일:
#  - 이 파일은 UTF-8 BOM 저장 필수(BOM 없으면 cp949로 읽혀 한글 깨짐).
#  - 네이티브 exe에 `2>&1` 금지. 성공 여부는 $LASTEXITCODE 로만 판정.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$logFile = Join-Path $here "cio_daily_mail.log"
function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding utf8
}

Log "=== cio_daily_mail 시작 ==="

try {
    # 1) 최신 데이터에서 시작 (cron이 하루 8회 push)
    & git fetch origin main | Out-Null
    & git pull --ff-only origin main | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Log "경고: git pull --ff-only 스킵 (미커밋 변경/분기) — 기존 로컬 데이터로 진행"
    }

    # 2) CIO 의견 생성 (구독 차감). 이미 같은 슬롯이 최신이면 스크립트가 알아서 스킵.
    #    과금 env가 상속되면 안 되므로 여기서 비운다(자식 프로세스에만 적용).
    $env:ANTHROPIC_API_KEY = ""
    $env:ANTHROPIC_BASE_URL = ""
    #    --use-cli: 토큰 env 없이 로그인된 로컬 CLI(구독)로 호출.
    & python briefing/generate_cio.py --use-cli --skip-if-current
    if ($LASTEXITCODE -ne 0) { throw "generate_cio.py 실패 (exit $LASTEXITCODE)" }

    # 3) 메일 발송 (같은 as_of+slot 이미 보냈으면 스킵)
    & python briefing/send_email_cio.py --skip-if-sent
    if ($LASTEXITCODE -ne 0) { throw "send_email_cio.py 실패 (exit $LASTEXITCODE)" }

    # 4) fm-cio.js 갱신분만 커밋·푸시 (다른 파일 절대 add 안 함)
    & git add fm-cio.js | Out-Null
    $staged = & git diff --cached --name-only
    if ($staged) {
        $msg = "auto: CIO 데일리 로컬 생성 {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm")
        & git commit -m $msg | Out-Null
        for ($i = 1; $i -le 3; $i++) {
            & git push | Out-Null
            if ($LASTEXITCODE -eq 0) { break }
            Log "push 실패($i/3) — cron 경합 가능성, reset --soft 후 재시도"
            & git fetch origin main | Out-Null
            & git reset --soft origin/main | Out-Null
            & git add fm-cio.js | Out-Null
            & git commit -m $msg | Out-Null
        }
    } else {
        Log "fm-cio.js 변경 없음 — 커밋 생략"
    }

    Log "=== 종료 (성공) ==="
} catch {
    Log "오류: $_"
    Log "=== 종료 (실패) ==="
    exit 1
}
