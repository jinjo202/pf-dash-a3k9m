# 롱숏포트 일일 시세 조회 헬퍼
# data.js의 pairs에 있는 모든 티커 + USDKRW의 최근 종가를 출력한다.
# 사용법: powershell -File update-prices.ps1
# 종목 + 지수/레짐 신호 (^KS11·^GSPC: 전략 B 오버레이 시가평가, ^VIX: 레짐 판정)
$tickers = @('005930.KS','000660.KS','005935.KS','373220.KS','006400.KS','TSM','INTC','WMT','TGT','KRW=X','^KS11','^GSPC','^VIX')
foreach ($t in $tickers) {
  try {
    $r = Invoke-RestMethod -Uri "https://query1.finance.yahoo.com/v8/finance/chart/$([uri]::EscapeDataString($t))?range=5d&interval=1d" -Headers @{'User-Agent'='Mozilla/5.0'} -TimeoutSec 15
    $m = $r.chart.result[0].meta
    $d = [DateTimeOffset]::FromUnixTimeSeconds($m.regularMarketTime).ToString('yyyy-MM-dd')
    Write-Output ("{0,-10} | {1,12} {2} | asOf {3}" -f $t, $m.regularMarketPrice, $m.currency, $d)
  } catch {
    Write-Output ("{0,-10} | FAILED: {1}" -f $t, $_.Exception.Message)
  }
}
