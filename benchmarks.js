// 시장 지수 YTD/일일 수익률 (공개 데이터, 평문). fetch_benchmarks.py로 갱신.
// KR 10Y는 수동 입력 (MANUAL_OVERRIDES) — 한국은행/금융투자협회에서 확인 후 갱신 필요.
window.BENCHMARKS = {
  "as_of": "2026-05-19",
  "indices": [
    {
      "name": "MSCI ACWI",
      "ticker": "ACWI",
      "category": "MSCI",
      "current": 152.76,
      "baseline": 141.49,
      "ytd_pct": 7.9652,
      "daily_pct": -1.0301,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 23.13,
        "pb": null,
        "roe": null,
        "src": "ACWI"
      }
    },
    {
      "name": "MSCI EM",
      "ticker": "EEM",
      "category": "MSCI",
      "current": 63.69,
      "baseline": 54.71,
      "ytd_pct": 16.4138,
      "daily_pct": -1.9701,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 17.27,
        "pb": 1.21,
        "roe": null,
        "src": "EEM"
      }
    },
    {
      "name": "KOSPI",
      "ticker": "^KS11",
      "category": "한국",
      "current": 7271.6602,
      "baseline": 4214.1699,
      "ytd_pct": 72.5526,
      "daily_pct": -3.2514,
      "as_of": "2026-05-19",
      "decimals": 0,
      "valuation": {
        "pe": 22.3,
        "pb": 1.93,
        "roe": null,
        "src": "EWY"
      }
    },
    {
      "name": "KOSDAQ",
      "ticker": "^KQ11",
      "category": "한국",
      "current": 1084.36,
      "baseline": 925.47,
      "ytd_pct": 17.1686,
      "daily_pct": -2.4057,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": null,
        "pb": null,
        "roe": null,
        "src": null
      }
    },
    {
      "name": "S&P 500",
      "ticker": "^GSPC",
      "category": "미국",
      "current": 7340.4902,
      "baseline": 6845.5,
      "ytd_pct": 7.2309,
      "daily_pct": -0.8451,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 27.5,
        "pb": 1.71,
        "roe": null,
        "src": "SPY"
      }
    },
    {
      "name": "NASDAQ",
      "ticker": "^IXIC",
      "category": "미국",
      "current": 25757.0332,
      "baseline": 23241.9902,
      "ytd_pct": 10.8211,
      "daily_pct": -1.279,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 34.01,
        "pb": 1.95,
        "roe": null,
        "src": "QQQ"
      }
    },
    {
      "name": "필라델피아 반도체",
      "ticker": "^SOX",
      "category": "미국",
      "current": 11034.8252,
      "baseline": 7083.1299,
      "ytd_pct": 55.7902,
      "daily_pct": -2.3684,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 44.45,
        "pb": 1.14,
        "roe": null,
        "src": "SOXX"
      }
    },
    {
      "name": "STOXX 600",
      "ticker": "^STOXX",
      "category": "유럽",
      "current": 611.38,
      "baseline": 592.78,
      "ytd_pct": 3.1378,
      "daily_pct": 0.1983,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 17.82,
        "pb": null,
        "roe": null,
        "src": "IEUR"
      }
    },
    {
      "name": "니케이 225",
      "ticker": "^N225",
      "category": "아시아",
      "current": 60550.5898,
      "baseline": 50339.4805,
      "ytd_pct": 20.2845,
      "daily_pct": -0.4363,
      "as_of": "2026-05-19",
      "decimals": 0,
      "valuation": {
        "pe": 18.4,
        "pb": 1.33,
        "roe": null,
        "src": "EWJ"
      }
    },
    {
      "name": "상해종합",
      "ticker": "000001.SS",
      "category": "아시아",
      "current": 4169.5376,
      "baseline": 3968.8401,
      "ytd_pct": 5.0568,
      "daily_pct": 0.92,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 12.64,
        "pb": null,
        "roe": null,
        "src": "MCHI"
      }
    },
    {
      "name": "USD/KRW",
      "ticker": "KRW=X",
      "category": "환율",
      "current": 1512.0601,
      "baseline": 1437.91,
      "ytd_pct": 5.1568,
      "daily_pct": 0.9959,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": null,
        "pb": null,
        "roe": null,
        "src": null
      }
    },
    {
      "name": "US 10Y",
      "ticker": "^TNX",
      "category": "금리",
      "current": 4.675,
      "baseline": 4.163,
      "ytd_pct": 12.2988,
      "daily_pct": 1.1248,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": null,
        "pb": null,
        "roe": null,
        "src": null
      }
    },
    {
      "name": "WTI 유가",
      "ticker": "CL=F",
      "category": "원자재",
      "current": 103.24,
      "baseline": 57.42,
      "ytd_pct": 79.798,
      "daily_pct": -4.988,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": null,
        "pb": null,
        "roe": null,
        "src": null
      }
    },
    {
      "name": "VIX",
      "ticker": "^VIX",
      "category": "변동성",
      "current": 17.97,
      "baseline": 14.95,
      "ytd_pct": 20.2007,
      "daily_pct": 0.8417,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": null,
        "pb": null,
        "roe": null,
        "src": null
      }
    },
    {
      "name": "KR 10Y",
      "ticker": "MANUAL",
      "category": "금리",
      "current": 3.3,
      "baseline": 2.95,
      "ytd_pct": 11.8644,
      "daily_pct": 0.9174,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": null,
        "pb": null,
        "roe": null,
        "src": null
      },
      "manual": true
    }
  ]
};
