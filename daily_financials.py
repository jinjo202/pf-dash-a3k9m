# -*- coding: utf-8 -*-
"""
데일리 유니버스(fetch_daily.py UNIVERSE) 전 종목 재무 스냅샷 → daily-financials.js
daily.html 종목 클릭 모달용. longshort/fetch_fundamentals.py 와 동일 구조/소스(야후 파이낸스).

소스: fundamentals-timeseries(연간 3y + 분기 8Q 매출/매출총이익/영업이익/순이익) + v8 chart(주가)
      + quoteSummary(crumb)에서 12M forward PER.
지표: PER=12M forward, PSR/OPM/GPM=후행 T12M. 통화는 티커 접미사로 판별(원화환산 fx 포함).
재무는 분기 단위라 매일 돌 필요 없음 — 주 1회(또는 수동) 갱신 권장. 실패 종목은 건너뜀(fail-safe).
"""
import json, ssl, sys, time, urllib.request, urllib.parse, http.cookiejar
from datetime import datetime, timezone
from fetch_daily import UNIVERSE

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CTX = ssl.create_default_context()
_OPENER = None
_CRUMB = None

# 통화별 원화 크로스 (해외 시총 원화환산용) — main에서 채움
FX_KRW = {"KRW": 1.0}
_FX_TICKERS = {"USD": "KRW=X", "JPY": "JPYKRW=X", "HKD": "HKDKRW=X", "CNY": "CNYKRW=X",
               "EUR": "EURKRW=X", "GBP": "GBPKRW=X", "CHF": "CHFKRW=X", "DKK": "DKKKRW=X"}


def ccy_of(t):
    for sfx, c in ((".KS", "KRW"), (".KQ", "KRW"), (".T", "JPY"), (".SS", "CNY"), (".SZ", "CNY"),
                   (".HK", "HKD"), (".DE", "EUR"), (".PA", "EUR"), (".AS", "EUR"), (".MC", "EUR"),
                   (".BR", "EUR"), (".MI", "EUR"), (".SW", "CHF"), (".L", "GBP"), (".CO", "DKK"),
                   (".OL", "NOK")):
        if t.endswith(sfx):
            return c
    return "USD"


def init_crumb():
    global _OPENER, _CRUMB
    cj = http.cookiejar.CookieJar()
    _OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    for seed in ("https://finance.yahoo.com", "https://fc.yahoo.com"):
        try:
            _OPENER.open(urllib.request.Request(seed, headers=UA), timeout=15).read()
        except Exception:
            pass
    try:
        _CRUMB = _OPENER.open(urllib.request.Request(
            "https://query1.finance.yahoo.com/v1/test/getcrumb", headers=UA), timeout=15).read().decode()
    except Exception as e:
        print(f"  crumb FAIL (forward PER 비활성): {e}", file=sys.stderr)
        _CRUMB = None


def forward_pe(ticker):
    if not _CRUMB:
        return None
    try:
        u = (f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(ticker)}"
             f"?modules=defaultKeyStatistics&crumb={urllib.parse.quote(_CRUMB)}")
        j = json.load(_OPENER.open(urllib.request.Request(u, headers=UA), timeout=20))
        v = j["quoteSummary"]["result"][0]["defaultKeyStatistics"].get("forwardPE")
        return v.get("raw") if isinstance(v, dict) else None
    except Exception:
        return None


TYPES = ("annualTotalRevenue,annualGrossProfit,annualOperatingIncome,annualNetIncomeCommonStockholders,"
         "quarterlyTotalRevenue,quarterlyGrossProfit,quarterlyOperatingIncome,quarterlyNetIncomeCommonStockholders,"
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


def init_fx():
    for ccy, tk in _FX_TICKERS.items():
        try:
            FX_KRW[ccy] = price_of(tk)[0]
        except Exception as e:
            print(f"  [warn] {tk} 실패: {e}", file=sys.stderr)
    # NOK: USD 경유
    try:
        usdnok = price_of("NOK=X")[0]
        if usdnok and FX_KRW.get("USD"):
            FX_KRW["NOK"] = FX_KRW["USD"] / usdnok
    except Exception as e:
        print(f"  [warn] NOK 실패: {e}", file=sys.stderr)


def main():
    init_crumb()
    init_fx()

    # 데일리 유니버스 전 종목 (미국 포함). name/sector 는 UNIVERSE 에서.
    stocks = []
    seen = set()
    for region, lst in UNIVERSE.items():
        for t, name, sector in lst:
            if t in seen:
                continue
            seen.add(t)
            stocks.append((t, name))

    result = {"asOf": None, "fx": FX_KRW, "tickers": {}}
    ok = 0
    for i, (t, name) in enumerate(stocks):
        ccy = ccy_of(t)
        try:
            px, asof = price_of(t)
            f = fundamentals(t)
            result["asOf"] = result["asOf"] or asof

            def series(kind):
                return {d: v for d, v in f.get(kind, [])}
            arev, agp, aop, ani = (series("annualTotalRevenue"), series("annualGrossProfit"),
                                    series("annualOperatingIncome"), series("annualNetIncomeCommonStockholders"))
            qrev, qgp, qop, qni = (series("quarterlyTotalRevenue"), series("quarterlyGrossProfit"),
                                    series("quarterlyOperatingIncome"), series("quarterlyNetIncomeCommonStockholders"))
            if not arev and not qrev:
                print(f"  skip {t}: 재무 없음", file=sys.stderr)
                continue

            annual = [{"y": d[:4], "rev": arev.get(d), "gp": agp.get(d), "op": aop.get(d), "ni": ani.get(d)}
                      for d in sorted(arev)][-3:]
            qdates = sorted(qrev)[-8:]
            quarters = [{"d": d, "q": q_label(d), "rev": qrev.get(d), "gp": qgp.get(d), "op": qop.get(d), "ni": qni.get(d)}
                        for d in qdates]

            sh = f.get("annualBasicAverageShares", [])
            shares = sh[-1][1] if sh else None
            mcap = px * shares if (shares and px) else None

            t12 = {}
            for key, m in (("rev", qrev), ("gp", qgp), ("op", qop), ("ni", qni)):
                vals = [m[d] for d in sorted(m)[-4:] if m.get(d) is not None]
                t12[key] = sum(vals) if len(vals) == 4 else None
            per_fwd = forward_pe(t)
            psr = (mcap / t12["rev"]) if (mcap and t12["rev"]) else None
            opm = (t12["op"] / t12["rev"] * 100) if (t12["op"] is not None and t12["rev"]) else None
            gpm = (t12["gp"] / t12["rev"] * 100) if (t12["gp"] is not None and t12["rev"]) else None
            mcapKrw = mcap * FX_KRW.get(ccy, 0) if mcap is not None else None

            result["tickers"][t] = {
                "name": name, "price": px, "priceCcy": ccy, "finCcy": ccy,
                "shares": shares, "adrRatio": 1, "isPref": False, "commonTicker": None,
                "mcap": mcap, "mcapKrw": mcapKrw,
                "perFwd": round(per_fwd, 1) if per_fwd else None,
                "psr": round(psr, 2) if psr else None,
                "opm": round(opm, 1) if opm is not None else None,
                "gpm": round(gpm, 1) if gpm is not None else None,
                "annual": annual, "quarters": quarters,
            }
            ok += 1
            time.sleep(0.25)  # 야후 rate-limit 완화
        except Exception as e:
            print(f"  FAILED {t}: {e}", file=sys.stderr)
            time.sleep(0.25)

    with open("daily-financials.js", "w", encoding="utf-8") as fp:
        fp.write("// 자동 생성: python daily_financials.py — 데일리 종목 재무 모달용. 수동 편집 금지.\n"
                 "window.DAILY_FIN = ")
        json.dump(result, fp, ensure_ascii=False, separators=(",", ":"))
        fp.write(";\n")
    print(f"[daily_financials] saved daily-financials.js — {ok}/{len(stocks)}종목, asOf {result['asOf']}")


if __name__ == "__main__":
    main()
