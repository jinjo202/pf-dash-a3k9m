"""
fetch_calendar.py — 캘린더 매크로/어닝 자동 갱신 (원문 공식 소스)

라이브 수치를 '이 PC'가 아니라 각 지표의 원문 공식 API에서 직접 당긴다.
FRED만 이 PC IP가 throttle될 뿐, BLS/Census/관세청 등은 호스트가 달라 정상.
GitHub Actions에서 돌리면 이 PC 제약과 무관하게 동작한다.

출력: calendar-auto.js  (window.CALENDAR_AUTO = { as_of, events:[...] })
      calendar.html 이 런타임에 CALENDAR(큐레이션)에 병합한다(중복은 날짜+타입 키로 제거).

소스별 자동화 상태
  ✅ 지금 실행 가능(키 불필요):  BLS(미 CPI·근원·실업·고용·임금), yfinance(어닝 일정)
  🔑 무료 API 키 필요(env):       관세청 수출(TRADE_API_KEY, data.go.kr)
                                  Census(CENSUS_API_KEY), BEA(BEA_API_KEY),
                                  KOSIS(KOSIS_API_KEY), ECOS 한국은행(ECOS_API_KEY)
  ⚠️ 무료 공식 API 없음:          컨센서스(예상치)·ISM PMI·DRAM 고정거래가 → 수동 오버레이

사용:
    python fetch_calendar.py                 # BLS+어닝만(키 없으면 나머지 스킵)
    python fetch_calendar.py --earn-tickers TSM,ASML,005930.KS
    TRADE_API_KEY=... python fetch_calendar.py   # 관세청까지
"""
import argparse
import datetime as dt
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "calendar-auto.js"
TODAY = dt.date.today()

# 기본 어닝 트래킹 유니버스(미·유·한·일·대) — 5개국 주요주
DEFAULT_EARN = [
    "TSM", "ASML", "NVDA", "MSFT", "AAPL", "AMZN", "META", "GOOGL", "TSLA",
    "005930.KS", "000660.KS",   # 삼성전자, SK하이닉스
    "8035.T", "6857.T",         # 도쿄일렉트론, 어드반테스트
    "2330.TW",                  # TSMC(대만 상장)
    "MC.PA", "NESN.SW",         # LVMH, 네슬레
]


def _http_json(url, data=None, headers=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ────────────────────────── BLS (미국) ──────────────────────────
def bls_series(series_ids, start, end, api_key=None):
    body = {"seriesid": series_ids, "startyear": str(start), "endyear": str(end)}
    if api_key:
        body["registrationkey"] = api_key
    r = _http_json(
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    if r.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS 실패: {r.get('status')} {r.get('message')}")
    out = {}
    for s in r["Results"]["series"]:
        rows = [d for d in s["data"] if d["period"].startswith("M")]
        rows.sort(key=lambda d: (int(d["year"]), int(d["period"][1:])))
        out[s["seriesID"]] = rows
    return out


def _nth_weekday(year, month, weekday, n):
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _next_month(y, m):
    return (y + 1, 1) if m == 12 else (y, m + 1)


def bls_events(api_key=None):
    """미 CPI/근원CPI/실업률/비농업고용/시간당임금 — 최근 실적치 + MoM/YoY."""
    ids = {
        "cpi_nsa": "CUUR0000SA0", "cpi_sa": "CUSR0000SA0",
        "core_nsa": "CUUR0000SA0L1E", "core_sa": "CUSR0000SA0L1E",
        "unrate": "LNS14000000", "payems": "CES0000000001",
        "ahe": "CES0500000003",
    }
    data = bls_series(list(ids.values()), TODAY.year - 1, TODAY.year, api_key)
    g = {k: data[v] for k, v in ids.items()}
    evs = []

    def latest(rows):
        return rows[-1] if rows else None

    def val(rows, i):
        return float(rows[i]["value"]) if rows and len(rows) >= -i else None

    def yoy(rows):
        if len(rows) < 13:
            return None
        return round((float(rows[-1]["value"]) / float(rows[-13]["value"]) - 1) * 100, 1)

    def mom(rows):
        if len(rows) < 2:
            return None
        return round((float(rows[-1]["value"]) / float(rows[-2]["value"]) - 1) * 100, 1)

    # 발표일 근사: 참조월 다음달 CPI≈13일, 고용≈첫째주 금요일
    def rel_cpi(row):
        y, m = _next_month(int(row["year"]), int(row["period"][1:]))
        return dt.date(y, m, 13)

    def rel_jobs(row):
        y, m = _next_month(int(row["year"]), int(row["period"][1:]))
        return _nth_weekday(y, m, 4, 1)  # 첫째주 금요일

    lc = latest(g["cpi_nsa"])
    if lc:
        evs.append(_macro_ev(
            rel_cpi(lc), "🇺🇸 미 CPI (헤드라인)", "% YoY", "BLS",
            actual=f"{yoy(g['cpi_nsa'])}%", prior=None,
            mom=f"{mom(g['cpi_sa'])}%", yoy=f"{yoy(g['cpi_nsa'])}%",
            ref=f"{lc['year']}-{lc['period'][1:]}", key="us_cpi",
            url="https://www.bls.gov/cpi/",
            detail=f"CPI-U 지수 {lc['value']} (NSA, {lc['periodName']} {lc['year']}). SA MoM {mom(g['cpi_sa'])}%.",
        ))
    lco = latest(g["core_nsa"])
    if lco:
        evs.append(_macro_ev(
            rel_cpi(lco), "🇺🇸 미 근원 CPI", "% YoY", "BLS",
            actual=f"{yoy(g['core_nsa'])}%", prior=None,
            mom=f"{mom(g['core_sa'])}%", yoy=f"{yoy(g['core_nsa'])}%",
            ref=f"{lco['year']}-{lco['period'][1:]}", key="us_core_cpi",
            url="https://www.bls.gov/cpi/",
            detail=f"근원(식품·에너지 제외) {lco['periodName']} {lco['year']}. SA MoM {mom(g['core_sa'])}%.",
        ))
    lu = latest(g["unrate"])
    if lu:
        prev = g["unrate"][-2]["value"] if len(g["unrate"]) >= 2 else None
        evs.append(_macro_ev(
            rel_jobs(lu), "🇺🇸 미 실업률", "%", "BLS",
            actual=f"{lu['value']}%", prior=f"{prev}%" if prev else None,
            mom=None, yoy=None, ref=f"{lu['year']}-{lu['period'][1:]}", key="us_unrate",
            url="https://www.bls.gov/ces/",
            detail=f"실업률 {lu['value']}% ({lu['periodName']} {lu['year']}, SA).",
        ))
    lp = g["payems"]
    if len(lp) >= 2:
        chg = round(float(lp[-1]["value"]) - float(lp[-2]["value"]), 0)
        prevchg = round(float(lp[-2]["value"]) - float(lp[-3]["value"]), 0) if len(lp) >= 3 else None
        evs.append(_macro_ev(
            rel_jobs(lp[-1]), "🇺🇸 미 비농업고용(NFP)", "천명", "BLS",
            actual=f"+{chg:.0f}K", prior=f"+{prevchg:.0f}K" if prevchg is not None else None,
            mom=None, yoy=None, ref=f"{lp[-1]['year']}-{lp[-1]['period'][1:]}", key="us_nfp",
            url="https://www.bls.gov/ces/",
            detail=f"비농업 취업자 전월대비 {chg:+.0f}천명 ({lp[-1]['periodName']} {lp[-1]['year']}, SA).",
        ))
    la = g["ahe"]
    if la:
        evs.append(_macro_ev(
            rel_jobs(la[-1]), "🇺🇸 미 시간당임금(AHE)", "% YoY", "BLS",
            actual=f"{yoy(la)}%", prior=None, mom=f"{mom(la)}%", yoy=f"{yoy(la)}%",
            ref=f"{la[-1]['year']}-{la[-1]['period'][1:]}", key="us_ahe",
            url="https://www.bls.gov/ces/",
            detail=f"시간당 평균임금 ${la[-1]['value']} (SA). MoM {mom(la)}% / YoY {yoy(la)}%.",
        ))
    return evs


def _macro_ev(d, title, unit, source, actual, prior, mom, yoy, ref, key, url, detail):
    return {
        "date": d.isoformat(), "type": "macro", "region": "US",
        "title": title, "unit": unit, "source": source, "importance": 3,
        "consensus": None, "prior": prior, "actual": actual, "mom": mom, "yoy": yoy,
        "released": True, "verified": True, "autokey": key, "auto": True,
        "ref_period": ref, "url": url, "detail": detail,
        "interp": "자동 수집(원문 공식 소스). 컨센서스·해석은 큐레이션 오버레이 참조.",
    }


# ────────────────────────── 어닝 일정 (yfinance) ──────────────────────────
def earnings_events(tickers):
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance 없음 — 어닝 스킵")
        return []
    lo, hi = TODAY - dt.timedelta(days=30), TODAY + dt.timedelta(days=120)
    evs = []
    for t in tickers:
        try:
            df = yf.Ticker(t).get_earnings_dates(limit=8)
            if df is None or df.empty:
                continue
            for idx in df.index:
                d = idx.date() if hasattr(idx, "date") else idx
                if lo <= d <= hi:
                    reg = ("KR" if t.endswith(".KS") else "JP" if t.endswith(".T")
                           else "TW" if t.endswith(".TW") else "EU" if ("." in t and not t.endswith(".TW")) else "US")
                    evs.append({
                        "date": d.isoformat(), "type": "earnings", "region": reg,
                        "ticker": t, "name": t, "importance": 2, "session": "amc",
                        "released": d < TODAY, "verified": False, "auto": True,
                        "epsEst": None, "revEst": None, "epsAct": None, "revAct": None,
                        "summary": None,
                        "irUrl": f"https://finance.yahoo.com/quote/{urllib.parse.quote(t)}",
                        "note": "yfinance 예상 실적발표일(변동 가능)",
                    })
        except Exception as e:
            print(f"  {t} 어닝 스킵: {str(e)[:50]}")
    return evs


# ────────────────────────── 관세청 수출 (data.go.kr, 키 필요) ──────────────────────────
def customs_export_events(api_key):
    """관세청 무역통계 OpenAPI. TRADE_API_KEY(data.go.kr) 필요.
    엔드포인트/파라미터는 발급 서비스에 맞춰 연결(스켈레톤)."""
    if not api_key:
        print("  TRADE_API_KEY 없음 — 관세청 수출 스킵 (data.go.kr에서 무료키 발급)")
        return []
    # TODO: 발급받은 '관세청_수출입실적' 서비스 URL/파라미터로 연결.
    #   1~10일·1~20일·월확정, 품목별(반도체 HS 8542) 조회.
    print("  관세청 어댑터: 키 감지 — 실제 엔드포인트 연결 필요(스켈레톤)")
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--earn-tickers", default=",".join(DEFAULT_EARN))
    ap.add_argument("--no-earn", action="store_true")
    args = ap.parse_args()

    events, log = [], []
    try:
        b = bls_events(os.environ.get("BLS_API_KEY"))
        events += b
        log.append(f"BLS {len(b)}건")
    except Exception as e:
        log.append(f"BLS 실패: {str(e)[:80]}")

    if not args.no_earn:
        e = earnings_events([t.strip() for t in args.earn_tickers.split(",") if t.strip()])
        events += e
        log.append(f"어닝 {len(e)}건")

    c = customs_export_events(os.environ.get("TRADE_API_KEY"))
    events += c
    if c:
        log.append(f"관세청 {len(c)}건")

    events.sort(key=lambda x: x["date"])
    payload = {
        "as_of": TODAY.isoformat(),
        "note": "원문 공식 소스 자동수집(BLS·yfinance·관세청). 컨센/ISM/DRAM은 무료 API 없음 → 큐레이션 오버레이.",
        "sources": log,
        "events": events,
    }
    OUT.write_text(
        "// 캘린더 자동수집 데이터 — fetch_calendar.py 생성 (공개, 평문)\n"
        f"window.CALENDAR_AUTO = {json.dumps(payload, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    print(f"생성: {OUT.name} · 총 {len(events)}건 · " + " · ".join(log))


if __name__ == "__main__":
    main()
