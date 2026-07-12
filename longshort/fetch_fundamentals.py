# -*- coding: utf-8 -*-
"""
종목 재무 스냅샷 수집 -> fundamentals.js 생성 (대시보드 종목 상세 모달용)
소스: 야후 파이낸스 fundamentals-timeseries (연간 3y + 분기 8Q 매출/영업이익/순이익) + v8 chart (주가/환율)
시총 = 주가 x 주식수(연간 기본주식수 근사, 일부 하드코딩 오버라이드). ADR은 원주 환산 비율 적용.
실행: python fetch_fundamentals.py  (일일 업데이트 시 주 1회 정도면 충분)
"""
import json, ssl, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0"}
CTX = ssl.create_default_context()

TICKERS = [
    # finCcy: 재무제표 통화, priceCcy: 주가 통화, adrRatio: 1 ADR = n 원주, sharesOverride: 주식수 강제
    {"t": "005930.KS", "name": "삼성전자",        "finCcy": "KRW", "priceCcy": "KRW"},
    {"t": "005935.KS", "name": "삼성전자우",      "finCcy": "KRW", "priceCcy": "KRW",
     "sharesOverride": 815974664, "isPref": True, "commonTicker": "005930.KS"},
    {"t": "000660.KS", "name": "SK하이닉스",      "finCcy": "KRW", "priceCcy": "KRW"},
    {"t": "373220.KS", "name": "LG에너지솔루션", "finCcy": "KRW", "priceCcy": "KRW", "sharesOverride": 234000000},
    {"t": "006400.KS", "name": "삼성SDI",         "finCcy": "KRW", "priceCcy": "KRW"},
    {"t": "TSM",       "name": "TSMC (ADR)",      "finCcy": "TWD", "priceCcy": "USD", "adrRatio": 5},
    {"t": "INTC",      "name": "Intel",           "finCcy": "USD", "priceCcy": "USD"},
    {"t": "WMT",       "name": "Walmart",         "finCcy": "USD", "priceCcy": "USD"},
    {"t": "TGT",       "name": "Target",          "finCcy": "USD", "priceCcy": "USD"},
]
TYPES = ("annualTotalRevenue,annualOperatingIncome,annualNetIncomeCommonStockholders,"
         "quarterlyTotalRevenue,quarterlyOperatingIncome,quarterlyNetIncomeCommonStockholders,"
         "annualBasicAverageShares")

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.load(r)

def price_of(ticker):
    j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?range=5d&interval=1d")
    m = j["chart"]["result"][0]["meta"]
    return m["regularMarketPrice"], datetime.fromtimestamp(m["regularMarketTime"], tz=timezone.utc).strftime("%Y-%m-%d")

def fundamentals(ticker):
    now = int(time.time())
    url = (f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
           f"{urllib.parse.quote(ticker)}?symbol={urllib.parse.quote(ticker)}&type={TYPES}"
           f"&period1=1546300800&period2={now}")
    j = get(url)
    out = {}
    for r in j["timeseries"]["result"]:
        typ = r["meta"]["type"][0]
        rows = [(x["asOfDate"], x["reportedValue"]["raw"]) for x in r.get(typ, []) if x and x.get("reportedValue")]
        out[typ] = rows
    return out

def q_label(d):
    y, m = int(d[:4]), int(d[5:7])
    return f"{y % 100}.{(m + 2) // 3}Q"

def main():
    fx = {}
    for sym, key in (("KRW=X", "USDKRW"), ("TWD=X", "USDTWD")):
        fx[key], _ = price_of(sym)
    result = {"asOf": None, "fx": fx, "tickers": {}}

    for cfg in TICKERS:
        t = cfg["t"]
        try:
            px, asof = price_of(t)
            f = fundamentals(t)
            result["asOf"] = result["asOf"] or asof

            def series(kind):
                m = {d: v for d, v in f.get(kind, [])}
                return m
            arev, aop, ani = series("annualTotalRevenue"), series("annualOperatingIncome"), series("annualNetIncomeCommonStockholders")
            qrev, qop, qni = series("quarterlyTotalRevenue"), series("quarterlyOperatingIncome"), series("quarterlyNetIncomeCommonStockholders")

            annual = [{"y": d[:4], "rev": arev.get(d), "op": aop.get(d), "ni": ani.get(d)}
                      for d in sorted(arev)][-3:]
            qdates = sorted(qrev)[-8:]
            quarters = [{"d": d, "q": q_label(d), "rev": qrev.get(d), "op": qop.get(d), "ni": qni.get(d)}
                        for d in qdates]

            shares = cfg.get("sharesOverride")
            if not shares:
                sh = f.get("annualBasicAverageShares", [])
                shares = sh[-1][1] if sh else None
            mcap = None
            if shares and px:
                # 야후 basic shares는 상장 단위(ADR 티커면 ADR 수) 기준 -> 그대로 곱한다
                mcap = px * shares  # priceCcy 기준

            # 밸류에이션: T12M (최근 4개 분기 합)
            t12 = {}
            for key, m in (("rev", qrev), ("op", qop), ("ni", qni)):
                vals = [m[d] for d in sorted(m)[-4:] if m.get(d) is not None]
                t12[key] = sum(vals) if len(vals) == 4 else None
            # 재무통화 -> 주가통화 변환 계수
            conv = 1.0
            if cfg["finCcy"] == "TWD" and cfg["priceCcy"] == "USD":
                conv = 1.0 / fx["USDTWD"]
            per = (mcap / (t12["ni"] * conv)) if (mcap and t12["ni"] and t12["ni"] > 0) else None
            psr = (mcap / (t12["rev"] * conv)) if (mcap and t12["rev"]) else None
            opm = (t12["op"] / t12["rev"] * 100) if (t12["op"] is not None and t12["rev"]) else None

            # 시총 원화 환산
            mcapKrw = None
            if mcap is not None:
                mcapKrw = mcap if cfg["priceCcy"] == "KRW" else mcap * fx["USDKRW"]

            result["tickers"][t] = {
                "name": cfg["name"], "price": px, "priceCcy": cfg["priceCcy"], "finCcy": cfg["finCcy"],
                "shares": shares, "adrRatio": cfg.get("adrRatio", 1),
                "isPref": cfg.get("isPref", False), "commonTicker": cfg.get("commonTicker"),
                "mcap": mcap, "mcapKrw": mcapKrw,
                "per": round(per, 1) if per else None,
                "psr": round(psr, 2) if psr else None,
                "opm": round(opm, 1) if opm is not None else None,
                "annual": annual, "quarters": quarters
            }
            print(f"  ok {t}: mcap={mcap and round(mcap/1e12,2)}T({cfg['priceCcy']}) "
                  f"PER={result['tickers'][t]['per']} 분기 {len(quarters)}개", file=sys.stderr)
        except Exception as e:
            print(f"  FAILED {t}: {e}", file=sys.stderr)

    with open("fundamentals.js", "w", encoding="utf-8") as fp:
        fp.write("// 자동 생성: python fetch_fundamentals.py — 수동 편집 금지\nwindow.FUNDAMENTALS = ")
        json.dump(result, fp, ensure_ascii=False)
        fp.write(";\n")
    print("saved: fundamentals.js")

if __name__ == "__main__":
    main()
