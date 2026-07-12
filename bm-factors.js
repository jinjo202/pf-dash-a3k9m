// 벤치마크 팩터 집계 (자동생성: fetch_bm_factors.py — 수동편집 금지)
// 프록시 ETF의 Morningstar 집계지표. ROE=(E/P)/(B/P) 도출.
window.BM_FACTORS = {
  "as_of": "2026-07-12",
  "source": "Morningstar fund aggregates via yfinance funds_data (proxy ETF)",
  "indices": {
    "MSCI ACWI": {
      "pe": 23.16,
      "pb": 3.68,
      "roe": 15.87,
      "proxy": "ACWI"
    },
    "S&P 500": {
      "pe": 26.87,
      "pb": 5.38,
      "roe": 20.03,
      "proxy": "IVV"
    },
    "KOSPI": {
      "pe": 19.98,
      "pb": 2.5,
      "roe": 12.51,
      "proxy": "EWY"
    }
  }
};
