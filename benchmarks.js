// 시장 지수 YTD/일일 수익률 (공개 데이터, 평문). fetch_benchmarks.py로 갱신.
window.BENCHMARKS = {
  "as_of": "2026-05-19",
  "indices": [
    {
      "name": "MSCI ACWI",
      "ticker": "ACWI",
      "category": "MSCI",
      "current": 152.89,
      "baseline": 141.49,
      "ytd_pct": 8.0571,
      "daily_pct": -0.9459,
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
      "current": 63.64,
      "baseline": 54.71,
      "ytd_pct": 16.3224,
      "daily_pct": -2.0471,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 17.26,
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
        "pe": 22.14,
        "pb": 1.91,
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
      "current": 7343.8701,
      "baseline": 6845.5,
      "ytd_pct": 7.2803,
      "daily_pct": -0.7994,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 27.52,
        "pb": 1.71,
        "roe": null,
        "src": "SPY"
      }
    },
    {
      "name": "NASDAQ",
      "ticker": "^IXIC",
      "category": "미국",
      "current": 25754.9004,
      "baseline": 23241.9902,
      "ytd_pct": 10.8119,
      "daily_pct": -1.2872,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 33.99,
        "pb": 1.95,
        "roe": null,
        "src": "QQQ"
      }
    },
    {
      "name": "필라델피아 반도체",
      "ticker": "^SOX",
      "category": "미국",
      "current": 10987.1396,
      "baseline": 7083.1299,
      "ytd_pct": 55.117,
      "daily_pct": -2.7904,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 44.25,
        "pb": 1.14,
        "roe": null,
        "src": "SOXX"
      }
    },
    {
      "name": "STOXX 600",
      "ticker": "^STOXX",
      "category": "유럽",
      "current": 611.98,
      "baseline": 592.78,
      "ytd_pct": 3.239,
      "daily_pct": 0.2966,
      "as_of": "2026-05-19",
      "decimals": 2,
      "valuation": {
        "pe": 17.83,
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
      "current": 1512.0699,
      "baseline": 1437.91,
      "ytd_pct": 5.1575,
      "daily_pct": 0.9966,
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
    }
  ]
};
