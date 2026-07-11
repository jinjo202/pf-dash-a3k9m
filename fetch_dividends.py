"""
배당주 탭(dividends.html)용 계량지표 수집.

- dividends-data.js 의 yf:"..." 심볼을 파싱 → yfinance 로 시세성 지표 조회
- 배당수익률은 yfinance dividendYield 필드(버전별로 %/소수 편차·누락)에 의존하지 않고
  **연배당금 / 현재주가 로 직접 계산**해 견고화 (fwd = dividendRate, ttm = trailingAnnualDividendRate)
- 결과를 dividends-quotes.js (window.DIVIDENDS_QUOTES) 로 저장 → dividends.html 이 로드해 덮어씀
- 실패 종목은 값 None (프런트에서 큐레이션 폴백값 사용)

사용법: python fetch_dividends.py            # 오늘자 있으면 생략
        python fetch_dividends.py --force    # 강제 재수집
의존성: yfinance (requirements.txt)
"""
import io, re, sys, json, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = Path(__file__).parent
SRC = HERE / "dividends-data.js"
OUT = HERE / "dividends-quotes.js"

import yfinance as yf


def extract_symbols(js: str):
    """dividends-data.js 에서 yf:"..." 심볼을 등장 순서로(중복제거) 추출."""
    seen, out = set(), []
    for m in re.finditer(r'yf:\s*"([^"]+)"', js):
        t = m.group(1).strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _num(v):
    try:
        f = float(v)
        return f if f == f else None  # NaN 컷
    except Exception:
        return None


def _pct(v):
    n = _num(v)
    return round(n, 2) if n is not None else None


def _rp(v):
    """가격 라운딩(캔들차트용): 크기에 맞춰 소수 자리 조정."""
    try:
        v = float(v)
        if v != v:
            return None
        a = abs(v)
        if a < 100:
            return round(v, 2)
        if a < 10000:
            return round(v, 1)
        return round(v)
    except Exception:
        return None


FREQ_LABEL = {12: "월", 4: "분기", 2: "반기", 1: "연"}

# 지역별 벤치마크 (yfinance 심볼)
BENCH = {"KOSPI": "^KS11", "SP500": "^GSPC", "STOXX600": "^STOXX"}


def _returns_from_hist(closes):
    """종가 시계열(pandas Series)로 1M/3M/YTD/1Y 수익률(%) 계산."""
    import pandas as pd
    out = {"r1m": None, "r3m": None, "rytd": None, "r1y": None}
    if closes is None or len(closes) < 2:
        return out
    s = closes.dropna()
    if len(s) < 2:
        return out
    last = float(s.iloc[-1])
    ld = s.index[-1]

    def asof(days=None, ytd=False):
        try:
            if ytd:
                sub = s[[ix.year == ld.year for ix in s.index]]
                if len(sub) == 0:
                    return None
                base = float(sub.iloc[0])
            else:
                t = ld - pd.Timedelta(days=days)
                sub = s[s.index <= t]
                if len(sub) == 0:
                    return None
                base = float(sub.iloc[-1])
            return round((last / base - 1) * 100, 1) if base > 0 else None
        except Exception:
            return None

    out["r1m"] = asof(30)
    out["r3m"] = asof(91)
    out["rytd"] = asof(ytd=True)
    out["r1y"] = asof(365)
    return out


def fetch_bench():
    """벤치마크 지수들의 기간수익률 수집 → {key: {r1m,r3m,rytd,r1y}}."""
    out = {}
    for key, sym in BENCH.items():
        try:
            h = yf.Ticker(sym).history(period="14mo")
            closes = h["Close"] if (h is not None and len(h)) else None
            out[key] = _returns_from_hist(closes)
        except Exception:
            out[key] = {"r1m": None, "r3m": None, "rytd": None, "r1y": None}
        time.sleep(0.4)
    return out


def _iso(d):
    """date/datetime → 'YYYY-MM-DD' 문자열."""
    try:
        return d.strftime("%Y-%m-%d")
    except Exception:
        try:
            return str(d)[:10]
        except Exception:
            return None


def _dividend_extras(tk, price, closes=None):
    """배당 이력·주기·최근/다음 일정을 계산해 dict 로 반환.
    .dividends 시계열은 주가와 동일 단위(런던=펜스, 한국=원)라 별도 보정 불필요.
    closes: 이미 조회한 종가 시계열(있으면 재조회 생략)."""
    ex = {"dps_ttm": None, "freq_n": None, "freq": None,
          "last_div": None, "next_exdiv": None, "next_paydiv": None, "hist": []}
    # ── 배당 이벤트(ex-date, 금액) 목록 ──
    events = []
    try:
        divs = tk.dividends
        if divs is not None and len(divs):
            for idx, v in divs.items():
                try:
                    events.append((idx.date(), float(v)))
                except Exception:
                    pass
    except Exception:
        events = []

    from datetime import date as _date
    today = datetime.now().date()

    if events:
        events.sort(key=lambda x: x[0])
        # 최근 배당(직전 ex-date)
        ld = events[-1]
        ex["last_div"] = {"date": _iso(ld[0]), "amt": round(ld[1], 4)}
        # 최근 12개월 배당 합 = 현재 연 주당배당(TTM)
        cut = today - timedelta(days=365)
        recent = [v for d, v in events if d >= cut]
        if recent:
            ex["dps_ttm"] = round(sum(recent), 4)
        # 주기 추론: 최근 ~400일 배당 횟수
        rc = [1 for d, v in events if d >= today - timedelta(days=400)]
        n = len(rc)
        fn = None
        if n >= 10:
            fn = 12
        elif n in (3, 4, 5):
            fn = 4
        elif n == 2:
            fn = 2
        elif n == 1:
            fn = 1
        ex["freq_n"] = fn
        ex["freq"] = FREQ_LABEL.get(fn)

    # ── 연도별 합계 + 그 해 배당수익률(연말 종가 기준) ──
    annual = {}
    for d, v in events:
        annual[d.year] = annual.get(d.year, 0.0) + v
    yearclose = {}
    try:
        cl = closes
        if cl is None:
            h = tk.history(period="5y")
            cl = h["Close"] if (h is not None and len(h)) else None
        if cl is not None and len(cl):
            for y in sorted(set([ix.year for ix in cl.index])):
                sub = cl[[ix.year == y for ix in cl.index]]
                if len(sub):
                    yearclose[int(y)] = float(sub.iloc[-1])
    except Exception:
        pass
    Y = today.year
    for y in (Y - 3, Y - 2, Y - 1):
        dps = annual.get(y)
        yc = yearclose.get(y)
        yld = round(dps / yc * 100, 2) if (dps and yc and yc > 0) else None
        ex["hist"].append({"yr": y, "dps": round(dps, 2) if dps else None, "yld": yld})

    # ── 다음 배당 일정(calendar) ──
    try:
        cal = tk.calendar or {}
        nx = cal.get("Ex-Dividend Date")
        pd_ = cal.get("Dividend Date")
        if isinstance(nx, (list, tuple)):
            nx = nx[0] if nx else None
        if isinstance(pd_, (list, tuple)):
            pd_ = pd_[0] if pd_ else None
        if nx:
            ex["next_exdiv"] = _iso(nx)
        if pd_:
            ex["next_paydiv"] = _iso(pd_)
    except Exception:
        pass
    return ex


def _pick(df, names):
    """income_stmt DataFrame에서 후보 행이름 중 존재하는 첫 값 반환(열=기간)."""
    for nm in names:
        if nm in df.index:
            return df.loc[nm]
    return None


def _financials(tk):
    """최근 3개년(연간) + 최근 4분기 매출/영업이익/순이익.
    반환: {ccy, a:[[기간,매출,영업이익,순이익]...], q:[...]} (값=보고통화 원화폐단위)."""
    REV = ["Total Revenue", "Operating Revenue", "Total Revenue As Reported"]
    OP = ["Operating Income", "Total Operating Income As Reported", "EBIT"]
    NI = ["Net Income", "Net Income Common Stockholders",
          "Net Income From Continuing Operation Net Minority Interest"]

    def series_at(row, col):
        if row is None:
            return None
        try:
            v = row.get(col)
            v = float(v)
            return v if v == v else None
        except Exception:
            return None

    def build(df, n, quarterly):
        if df is None or df.empty:
            return []
        rev, op, ni = _pick(df, REV), _pick(df, OP), _pick(df, NI)
        cols = list(df.columns)[:n]
        rows = []
        for c in cols:
            try:
                if quarterly:
                    label = f"{str(c.year)[2:]}Q{(c.month - 1)//3 + 1}"
                else:
                    label = str(c.year)
            except Exception:
                label = str(c)[:7]
            rows.append([label, series_at(rev, c), series_at(op, c), series_at(ni, c)])
        return rows

    out = {"ccy": None, "a": [], "q": []}
    try:
        out["a"] = build(tk.income_stmt, 3, False)
    except Exception:
        out["a"] = []
    try:
        out["q"] = build(tk.quarterly_income_stmt, 4, True)
    except Exception:
        out["q"] = []
    if not out["a"] and not out["q"]:
        return None
    return out


def fetch_one(sym: str):
    """(dict) 반환. 실패시 값 None."""
    q = {"price": None, "ccy": "", "yld": None, "yldT": None, "payout": None,
         "per": None, "pbr": None, "mcap": None,
         "r1m": None, "r3m": None, "rytd": None, "ret1y": None,
         "drate": None, "exdiv": None,
         "dps_ttm": None, "freq_n": None, "freq": None,
         "last_div": None, "next_exdiv": None, "next_paydiv": None, "hist": [],
         "ohlc": [], "avg3y": None, "yld3avg": None, "fin": None}
    info = {}
    tk = None
    for attempt in range(3):
        try:
            tk = yf.Ticker(sym)
            info = tk.info or {}
            if info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"):
                break
        except Exception:
            info = {}
        time.sleep(1.2)
    if tk is None:
        tk = yf.Ticker(sym)

    price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice")) or _num(info.get("previousClose"))
    q["price"] = round(price, 2) if price else None
    ccy = info.get("currency") or ""
    q["ccy"] = ccy

    # 연배당금 (forward / ttm)
    drate = _num(info.get("dividendRate"))
    trate = _num(info.get("trailingAnnualDividendRate"))
    # ⚠️ 런던(LSE) GBp 종목: 주가는 펜스(pence)인데 dividendRate 는 파운드(GBP)로 와
    #   그대로 나누면 수익률이 100배 작게 나온다 → 배당금을 펜스로 정규화(×100)
    if ccy in ("GBp", "GBX"):
        if drate is not None:
            drate *= 100
        if trate is not None:
            trate *= 100
    q["drate"] = drate if drate is not None else trate

    if price and price > 0:
        if drate is not None:
            q["yld"] = round(drate / price * 100, 2)
        if trate is not None:
            q["yldT"] = round(trate / price * 100, 2)
    # dividendYield 필드로 폴백/보정: 계산값 누락 또는 비정상(<0.5%)이면 사용
    #   (dividendYield 는 이 yfinance 버전에서 % 단위, 예: 5.3 = 5.3%)
    dy = _num(info.get("dividendYield"))
    if dy is not None:
        dy_pct = dy if dy > 1 else dy * 100
        if q["yld"] is None or q["yld"] < 0.5:
            q["yld"] = round(dy_pct, 2)

    pr = _num(info.get("payoutRatio"))
    q["payout"] = round(pr * 100, 1) if pr is not None else None

    per = _num(info.get("trailingPE")) or _num(info.get("forwardPE"))
    if per is not None and (per <= 0 or per > 500):
        per = None
    q["per"] = round(per, 1) if per is not None else None

    pbr = _num(info.get("priceToBook"))
    if pbr is not None and (pbr <= 0 or pbr > 100):
        pbr = None
    q["pbr"] = round(pbr, 2) if pbr is not None else None

    q["mcap"] = info.get("marketCap")

    # 종가 시계열 1회 조회 → 기간수익률 + 배당이력(연말종가) 공용
    closes = None
    try:
        h5 = tk.history(period="5y")
        closes = h5["Close"] if (h5 is not None and len(h5)) else None
    except Exception:
        closes = None
    rets = _returns_from_hist(closes)
    q["r1m"], q["r3m"], q["rytd"], q["ret1y"] = rets["r1m"], rets["r3m"], rets["rytd"], rets["r1y"]
    if q["ret1y"] is None:
        chg = _num(info.get("52WeekChange"))
        if chg is not None:
            q["ret1y"] = round(chg * 100, 1)

    # 과거 3년 평균주가 + 그 대비 배당률(정상화 배당률): 고평가/저평가 판단 보조
    try:
        if closes is not None and len(closes):
            a3 = closes.dropna().tail(756)  # 약 3년(252*3) 거래일
            if len(a3):
                avg3 = float(a3.mean())
                q["avg3y"] = _rp(avg3)
                if drate is not None and avg3 > 0:
                    q["yld3avg"] = round(drate / avg3 * 100, 2)
    except Exception:
        pass

    # 최근 250거래일(~1년) OHLC (캔들차트·이평선·RSI용) — [MM-DD, O, H, L, C]
    #   MA60/RSI14 는 룩백이 필요해 넉넉히 저장, 프런트에서 기간(1M/3M/6M/1Y) 슬라이스
    try:
        if h5 is not None and len(h5):
            tail = h5.tail(250)
            oh = []
            for idx, row in tail.iterrows():
                o, hi, lo, cl = _rp(row.get("Open")), _rp(row.get("High")), _rp(row.get("Low")), _rp(row.get("Close"))
                if None in (o, hi, lo, cl):
                    continue
                oh.append([idx.strftime("%m-%d"), o, hi, lo, cl])
            q["ohlc"] = oh
    except Exception:
        pass

    ex = info.get("exDividendDate")
    if ex:
        try:
            q["exdiv"] = datetime.fromtimestamp(int(ex), tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            q["exdiv"] = None

    # ── 배당 이력·주기·최근/다음 일정 (종가 재사용) ──
    extra = _dividend_extras(tk, price, closes)
    q.update(extra)
    # 주기 라벨: 라이브 추론값 우선(없으면 프런트의 큐레이션 freq 사용)
    # TTM 주당배당이 있으면 이를 표시용 DPS 로도 사용(단위=주가 통화, .L은 pence)
    if q.get("dps_ttm") is None and q.get("drate") is not None:
        q["dps_ttm"] = round(q["drate"], 4)
    # TTM 배당률 폴백: trailingAnnualDividendRate 누락 시(주로 KR) TTM 배당금/주가로 계산
    if q.get("yldT") is None and q.get("dps_ttm") and price and price > 0:
        q["yldT"] = round(q["dps_ttm"] / price * 100, 2)

    # ── 재무: 최근 3년(연간) + 4분기 매출/영업이익/순이익 ──
    try:
        fin = _financials(tk)
        if fin:
            fin["ccy"] = info.get("financialCurrency") or q.get("ccy") or ""
            q["fin"] = fin
    except Exception:
        pass
    return q


def _kst_today():
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")


def already_today():
    if not OUT.exists():
        return False
    try:
        m = re.search(r'"as_of":\s*"(\d{4}-\d{2}-\d{2})', OUT.read_text(encoding="utf-8"))
        return bool(m) and m.group(1) == _kst_today()
    except Exception:
        return False


def main():
    if "--force" not in sys.argv and already_today():
        print("skip: dividends-quotes 이미 오늘자 — 재수집 생략 (--force 로 강제)")
        return
    js = SRC.read_text(encoding="utf-8")
    syms = extract_symbols(js)
    print(f"배당 유니버스 {len(syms)}개 심볼 수집 시작…")
    data, ok, miss = {}, 0, 0
    for i, s in enumerate(syms, 1):
        q = fetch_one(s)
        data[s] = q
        if q["price"] is not None:
            ok += 1
        else:
            miss += 1
            print(f"  ⚠ miss: {s}")
        if i % 10 == 0:
            print(f"  {i}/{len(syms)} … (ok {ok}, miss {miss})")
        time.sleep(0.5)
    print("벤치마크 지수 수집…")
    bench = fetch_bench()
    kst = timezone(timedelta(hours=9))
    as_of = datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")
    payload = {"as_of": as_of, "source": "yfinance", "data": data, "bench": bench}
    OUT.write_text(
        "// 배당주 계량지표 (yfinance, 시세성). fetch_dividends.py 로 갱신. 배당수익률=연배당/주가 직접계산.\n"
        "window.DIVIDENDS_QUOTES = " + json.dumps(payload, ensure_ascii=False, allow_nan=False) + ";\n",
        encoding="utf-8",
    )
    print(f"완료: {OUT.name} 작성 (ok {ok} / miss {miss} / 총 {len(syms)}) · {as_of}")


if __name__ == "__main__":
    main()
