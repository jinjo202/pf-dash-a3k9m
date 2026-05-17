# 포트폴리오 서버 인프라 설정 (1회 실행, 관리자 권한 필요)
# - Windows Firewall에 인바운드 8000 포트 허용
# - 로그인 시 자동으로 serve.py 백그라운드 실행 등록

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8000

# 1) qrcode 패키지 (선택)
Write-Host "[1/4] qrcode + pillow 설치 시도..."
python -m pip install --quiet qrcode pillow 2>&1 | Out-Null

# 2) 방화벽 규칙
$ruleName = "Portfolio Dashboard Server (TCP $port)"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[2/4] 방화벽 규칙 이미 존재: $ruleName"
} else {
    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $port `
        -Action Allow `
        -Profile Private,Domain | Out-Null
    Write-Host "[2/4] 방화벽 규칙 추가 (TCP $port, Private/Domain만 허용)"
}

# 3) 자동 시작 작업 등록
$taskName = "Portfolio_Dashboard_Server"
$pyw = Get-Command pythonw -ErrorAction SilentlyContinue
$exe = if ($pyw) { $pyw.Source } else { (Get-Command python).Source }
$script = Join-Path $here "serve.py"

$trigger  = New-ScheduledTaskTrigger -AtLogon
$action   = New-ScheduledTaskAction -Execute $exe -Argument "`"$script`" $port" -WorkingDirectory $here
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $taskName `
    -Trigger $trigger -Action $action -Settings $settings `
    -Description "포트폴리오 대시보드 로컬 HTTP 서버 (port $port)" -Force | Out-Null
Write-Host "[3/4] 자동 시작 등록: $taskName (실행 파일=$($exe))"

# 4) 즉시 시작
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
Write-Host "[4/4] 서버 시작됨"

# LAN IP 안내
$ip = (Test-Connection -ComputerName 8.8.8.8 -Count 1 -ErrorAction SilentlyContinue).IPV4Address.IPAddressToString
if (-not $ip) {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress -notmatch '^(127|169)\.' -and $_.PrefixOrigin -ne 'WellKnown'
    } | Select-Object -First 1).IPAddress
}

Write-Host ""
Write-Host "========================================================"
Write-Host "  접속 URL"
Write-Host "========================================================"
Write-Host "  PC:    http://localhost:$port/portfolio.html"
Write-Host "  Phone: http://$($ip):$port/portfolio.html  (같은 WiFi)"
Write-Host "  QR:    $here\phone_qr.png  (생성됐다면 폰 카메라로 스캔)"
Write-Host ""
Write-Host "  중지: Stop-ScheduledTask -TaskName $taskName"
Write-Host "  제거: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
Write-Host "        Remove-NetFirewallRule -DisplayName `"$ruleName`""
