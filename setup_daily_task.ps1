# 매일 가격 자동 업데이트 - Windows 작업 스케줄러 등록
# 실행: 관리자 권한 PowerShell에서 한 번만 실행

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$psExe = "powershell.exe"
$script = Join-Path $here "daily_run.ps1"
$taskName  = "Portfolio_Daily_Update"

# 매일 오후 3시 35분 (KOSPI 마감 15:30 직후) — 한국 종목 금일 손익 즉시 반영
$trigger = New-ScheduledTaskTrigger -Daily -At 3:35pm

$action = New-ScheduledTaskAction `
    -Execute $psExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $here

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName `
    -Trigger $trigger -Action $action -Settings $settings `
    -Description "포트폴리오 가격 자동 갱신 + 암호화 + Git push" -Force

Write-Host "등록 완료: $taskName"
Write-Host "  스크립트: $script"
Write-Host "수동 실행: Start-ScheduledTask -TaskName $taskName"
Write-Host "확인:      Get-ScheduledTaskInfo -TaskName $taskName"
Write-Host "삭제:      Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
