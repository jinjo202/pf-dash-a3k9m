# 매일 가격 자동 업데이트 - Windows 작업 스케줄러 등록
# 실행: 관리자 권한 PowerShell에서 한 번만 실행

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = (Get-Command python).Source
$script    = Join-Path $here "update_prices.py"
$taskName  = "Portfolio_Update_Prices"

# 매일 오후 6시 (한국 장 마감 + 약간 여유) — 원하면 수정
$trigger = New-ScheduledTaskTrigger -Daily -At 6:00pm

$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "`"$script`"" `
    -WorkingDirectory $here

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName `
    -Trigger $trigger -Action $action -Settings $settings `
    -Description "포트폴리오 가격 자동 갱신 (yfinance)" -Force

Write-Host "등록 완료: $taskName"
Write-Host "  Python: $pythonExe"
Write-Host "  스크립트: $script"
Write-Host "수동 실행: Start-ScheduledTask -TaskName $taskName"
Write-Host "확인:      Get-ScheduledTaskInfo -TaskName $taskName"
Write-Host "삭제:      Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
