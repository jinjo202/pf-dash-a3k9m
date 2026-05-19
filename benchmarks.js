// 시장 지수 YTD/일일 수익률 (공개 데이터, 평문). fetch_benchmarks.py로 갱신.
window.BENCHMARKS = {
  "as_of": "2026-05-19",
  "indices": [
    {
      "name": "MSCI ACWI",
      "ticker": "ACWI",
      "category": "MSCI",
      "current": 152.945,
      "baseline": 141.49,
      "ytd_pct": 8.096,
      "daily_pct": -0.9103,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 23.15,
        "pb": null,
        "roe": null,
        "src": "ACWI"
      }
    },
    {
      "name": "MSCI EM",
      "ticker": "EEM",
      "category": "MSCI",
      "current": 63.695,
      "baseline": 54.71,
      "ytd_pct": 16.423,
      "daily_pct": -1.9624,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 17.28,
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
        "pe": 22.22,
        "pb": 1.92,
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
      "current": 7348.9902,
      "baseline": 6845.5,
      "ytd_pct": 7.3551,
      "daily_pct": -0.7302,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 27.54,
        "pb": 1.71,
        "roe": null,
        "src": "SPY"
      }
    },
    {
      "name": "NASDAQ",
      "ticker": "^IXIC",
      "category": "미국",
      "current": 25788.7891,
      "baseline": 23241.9902,
      "ytd_pct": 10.9577,
      "daily_pct": -1.1573,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 34.05,
        "pb": 1.95,
        "roe": null,
        "src": "QQQ"
      }
    },
    {
      "name": "필라델피아 반도체",
      "ticker": "^SOX",
      "category": "미국",
      "current": 11036.9854,
      "baseline": 7083.1299,
      "ytd_pct": 55.8207,
      "daily_pct": -2.3493,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 44.44,
        "pb": 1.14,
        "roe": null,
        "src": "SOXX"
      }
    },
    {
      "name": "STOXX 600",
      "ticker": "^STOXX",
      "category": "유럽",
      "current": 611.14,
      "baseline": 592.78,
      "ytd_pct": 3.0973,
      "daily_pct": 0.159,
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
        "pe": 18.41,
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
        "pe": 12.65,
        "pb": null,
        "roe": null,
        "src": "MCHI"
      }
    },
    {
      "name": "USD/KRW",
      "ticker": "KRW=X",
      "category": "환율",
      "current": 1511.88,
      "baseline": 1437.91,
      "ytd_pct": 5.1443,
      "daily_pct": 0.9839,
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
      "current": 4.683,
      "baseline": 4.163,
      "ytd_pct": 12.491,
      "daily_pct": 1.2979,
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
      "current": 103.06,
      "baseline": 57.42,
      "ytd_pct": 79.4845,
      "daily_pct": -5.1537,
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
      "current": 18.01,
      "baseline": 14.95,
      "ytd_pct": 20.4682,
      "daily_pct": 1.0662,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": null,
        "pb": null,
        "roe": null,
        "src": null
      }
    }
  ]
};
