# -*- coding: utf-8 -*-
"""
펀드매니저 탭 — 종목별 손익계산서(Income Statement) + 컨센서스 estimates 수집.
- yfinance에서 최근 5개 회계연도 연간 IS(실적) + 최근 분기 실적 + 컨센서스(당기/차기 분기·연도) 수집
- fm-financials.js (window.FM_FINANCIALS) 생성. fm.html이 종목명 클릭 시 모달로 표시.

⚠ 큐레이션/수동 갱신 스크립트(cron 대상 아님). 분기 실적 시즌 후 재실행:
    python fetch_fm_financials.py

종목 유니버스는 fm-data.js의 stocks + themes[].plays(stock)와 동기화 유지(아래 STOCKS).
yfinance 무료 데이터는 컨센서스를 '당분기/차분기/당해연도/차기연도'까지만 제공(2년치 분기 그리드는 불가).
"""
import json
import sys
import io
import time
import datetime as dt

import re as _re
from io import StringIO

import requests
import yfinance as yf
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      "Referer": "https://finance.naver.com/"}

# 한국 종목 한글명(FnGuide 데이터에 함께 표기)
KR_NAMES = {
    "005930 KS": "삼성전자", "000660 KS": "SK하이닉스", "012450 KS": "한화에어로스페이스",
    "005380 KS": "현대차", "034020 KS": "두산에너빌리티", "247540 KS": "에코프로비엠",
    "329180 KS": "HD현대중공업", "207940 KS": "삼성바이오로직스", "105560 KS": "KB금융",
    "042660 KS": "한화오션",
}

# (표시 티커, yfinance 심볼) — fm-data.js와 동기화
STOCKS = [
    ("NVDA", "NVDA"), ("GOOGL", "GOOGL"), ("MSFT", "MSFT"), ("AVGO", "AVGO"),
    ("TSM", "TSM"), ("ASML", "ASML"), ("AMD", "AMD"), ("MU", "MU"),
    ("AMAT", "AMAT"), ("COHR", "COHR"), ("LITE", "LITE"), ("GLW", "GLW"),
    ("GEV", "GEV"), ("VST", "VST"),
    ("005930 KS", "005930.KS"), ("000660 KS", "000660.KS"), ("012450 KS", "012450.KS"),
    ("005380 KS", "005380.KS"), ("034020 KS", "034020.KS"), ("247540 KS", "247540.KS"),
    ("329180 KS", "329180.KS"), ("207940 KS", "207940.KS"), ("105560 KS", "105560.KS"),
    ("042660 KS", "042660.KS"),
]


def row(df, *names):
    """index 이름 후보 중 처음 매칭되는 시리즈 반환(없으면 None)."""
    if df is None:
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def num(v):
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def annual_block(t):
    isa = None
    try:
        isa = t.income_stmt
    except Exception:
        isa = None
    if isa is None or isa.shape[1] == 0:
        return None
    cols = list(isa.columns)
    # 최신→과거 순으로 오므로 과거→최신으로 뒤집어 표시
    cols = sorted(cols)
    years = [c.year for c in cols]
    rev = row(isa, "Total Revenue", "Operating Revenue")
    gp = row(isa, "Gross Profit")
    oi = row(isa, "Operating Income", "Total Operating Income As Reported")
    ni = row(isa, "Net Income", "Net Income Common Stockholders")
    eps = row(isa, "Diluted EPS", "Basic EPS")

    def series(s):
        return [num(s[c]) if s is not None else None for c in cols]

    return {
        "years": years,
        "fy_end_month": cols[-1].month,
        "revenue": series(rev),
        "gross_profit": series(gp),
        "operating_income": series(oi),
        "net_income": series(ni),
        "diluted_eps": series(eps),
    }


def quarter_actuals(t):
    try:
        q = t.quarterly_income_stmt
    except Exception:
        q = None
    if q is None or q.shape[1] == 0:
        return None
    cols = sorted(list(q.columns))[-5:]  # 최근 5개 분기
    rev = row(q, "Total Revenue", "Operating Revenue")
    oi = row(q, "Operating Income", "Total Operating Income As Reported")
    ni = row(q, "Net Income", "Net Income Common Stockholders")
    eps = row(q, "Diluted EPS", "Basic EPS")

    def series(s):
        return [num(s[c]) if s is not None else None for c in cols]

    return {
        "ends": [c.strftime("%Y-%m") for c in cols],
        "revenue": series(rev),
        "operating_income": series(oi),
        "net_income": series(ni),
        "diluted_eps": series(eps),
        "last_end": cols[-1].strftime("%Y-%m-%d"),
    }


def estimates(t, last_fy_year, last_q_end, stmt_currency, last_act_eps, last_act_rev):
    out = {"annual": None, "quarter": None, "eps_ok": True, "rev_ok": True, "note": ""}
    try:
        ee = t.earnings_estimate
    except Exception:
        ee = None
    try:
        re = t.revenue_estimate
    except Exception:
        re = None

    def g(df, period, col):
        try:
            if df is not None and period in df.index and col in df.columns:
                return num(df.loc[period, col])
        except Exception:
            pass
        return None

    def gstr(df, col):
        try:
            if df is not None and col in df.columns and len(df):
                return str(df[col].iloc[0])
        except Exception:
            pass
        return None

    # 데이터 정합성 가드: 통화 불일치만 차단(예: TSM은 재무제표 TWD인데 컨센서스 EPS는 USD ADR 기준
    # → 비교 불가). 스케일 기반 차단은 적용하지 않음 — 2026 AI/메모리 슈퍼사이클로 추정치가 실적 대비
    # 크게 점프하는 것이 정상이며(실가격으로 PER 정합 확인), 임의 스케일 컷오프는 정상 데이터를 가린다.
    eps_cur = gstr(ee, "currency")
    eps0 = g(ee, "0y", "avg")
    rev0 = g(re, "0y", "avg")
    notes = []
    if eps_cur and stmt_currency and eps_cur != stmt_currency:
        out["eps_ok"] = False
        notes.append("EPS 컨센서스 통화(%s)가 재무제표 통화(%s)와 불일치 — 비교 불가" % (eps_cur, stmt_currency))
    out["note"] = " · ".join(notes)
    out["eps_currency"] = eps_cur

    # 연간: 0y=당해(미보고) 회계연도, +1y=차기. 라벨연도 = 최근 실적연도 +1/+2
    if last_fy_year:
        out["annual"] = {
            "years": [last_fy_year + 1, last_fy_year + 2],
            "eps_avg": [g(ee, "0y", "avg"), g(ee, "+1y", "avg")],
            "eps_low": [g(ee, "0y", "low"), g(ee, "+1y", "low")],
            "eps_high": [g(ee, "0y", "high"), g(ee, "+1y", "high")],
            "eps_growth": [g(ee, "0y", "growth"), g(ee, "+1y", "growth")],
            "rev_avg": [g(re, "0y", "avg"), g(re, "+1y", "avg")],
            "n_analysts": [g(ee, "0y", "numberOfAnalysts"), g(ee, "+1y", "numberOfAnalysts")],
        }

    # 분기: 0q=당분기, +1q=차분기. 종료월 = 최근 실적분기 +3/+6개월
    q_ends = ["(E)", "(E)"]
    if last_q_end:
        base = pd.Timestamp(last_q_end)
        q_ends = [(base + pd.DateOffset(months=3)).strftime("%Y-%m"),
                  (base + pd.DateOffset(months=6)).strftime("%Y-%m")]
    out["quarter"] = {
        "ends": q_ends,
        "eps_avg": [g(ee, "0q", "avg"), g(ee, "+1q", "avg")],
        "eps_low": [g(ee, "0q", "low"), g(ee, "+1q", "low")],
        "eps_high": [g(ee, "0q", "high"), g(ee, "+1q", "high")],
        "eps_yearago": [g(ee, "0q", "yearAgoEps"), g(ee, "+1q", "yearAgoEps")],
        "rev_avg": [g(re, "0q", "avg"), g(re, "+1q", "avg")],
        "n_analysts": [g(ee, "0q", "numberOfAnalysts"), g(ee, "+1q", "numberOfAnalysts")],
    }
    return out


def _kr_billion(v):
    """FnGuide 표기는 억원 단위 → 원(raw)으로 변환."""
    n = num(v)
    return None if n is None else n * 1e8


def _pick_fn_table(tabs, ptype):
    """FnGuide 표 중 연결 기준 + 해당 기간유형(Annual / Net Quarter) + 추정(E) 컬럼이 가장 많은 표."""
    best, bestE = None, -1
    for t in tabs:
        if not isinstance(t.columns, pd.MultiIndex):
            continue
        if "연결" not in str(t.columns[0][0]):
            continue
        tops = [str(c[0]) for c in t.columns[1:]]
        subs = [str(c[1]) for c in t.columns[1:]]
        if not any(tp == ptype for tp in tops):
            continue
        nE = sum(("(E)" in s) for tp, s in zip(tops, subs) if tp == ptype)
        nCols = sum(1 for tp in tops if tp == ptype)
        if nCols >= 3 and nE > bestE:
            best, bestE = t, nE
    return best


def _fn_rows(t, ptype):
    """선택된 표에서 (실적컬럼, 추정컬럼) 인덱스/라벨과 라벨→행 매핑 반환."""
    cols = [(str(c[0]), str(c[1])) for c in t.columns]
    labels = [str(x).replace("\xa0", " ").strip() for x in t.iloc[:, 0].tolist()]
    rowmap = {}
    for i, lab in enumerate(labels):
        rowmap.setdefault(lab, i)
    act, est = [], []
    for ci, (top, sub) in enumerate(cols):
        if top != ptype:
            continue
        (est if "(E)" in sub else act).append((ci, sub))
    return rowmap, act, est


def fnguide(disp):
    """한국 종목: FnGuide Financial Highlight(연결)에서 5년 연간 실적 + 2026E/2027E + 분기 수집."""
    code6 = disp.split()[0]
    url = ("https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A%s"
           "&cID=&MenuYn=Y&ReportGB=&NewMenuID=11&stkGb=701" % code6)
    r = requests.get(url, headers={"User-Agent": UA["User-Agent"]}, timeout=15)
    r.encoding = "utf-8"
    tabs = pd.read_html(StringIO(r.text))

    def yr(sub):
        m = _re.search(r"(\d{4})", sub)
        return int(m.group(1)) if m else None

    def qlabel(sub):
        m = _re.search(r"(\d{4})/(\d{2})", sub)
        return ("%s-%s" % (m.group(1), m.group(2))) if m else sub

    def val(t, rowmap, ci, label, kind="money"):
        labels = label if isinstance(label, (list, tuple)) else [label]
        i = None
        for lb in labels:
            if lb in rowmap:
                i = rowmap[lb]; break
        if i is None:
            return None
        v = t.iloc[i, ci]
        return _kr_billion(v) if kind == "money" else num(v)

    REV = ["매출액", "영업수익", "이자수익"]   # 은행·증권은 매출액 대신 영업수익

    # 연간
    at = _pick_fn_table(tabs, "Annual")
    annual = None
    est_annual = None
    if at is not None:
        rm, act, est = _fn_rows(at, "Annual")
        annual = {
            "years": [yr(s) for _, s in act],
            "fy_end_month": 12,
            "revenue": [val(at, rm, ci, REV) for ci, _ in act],
            "gross_profit": [val(at, rm, ci, "매출총이익") for ci, _ in act],
            "operating_income": [val(at, rm, ci, "영업이익") for ci, _ in act],
            "net_income": [val(at, rm, ci, "당기순이익") for ci, _ in act],
            "diluted_eps": [val(at, rm, ci, "EPS(원)", "num") for ci, _ in act],
        }
        est = est[:2]  # 2026E, 2027E
        if est:
            est_annual = {
                "years": [yr(s) for _, s in est],
                "eps_avg": [val(at, rm, ci, "EPS(원)", "num") for ci, _ in est],
                "eps_low": [None for _ in est], "eps_high": [None for _ in est],
                "eps_growth": [None for _ in est],
                "rev_avg": [val(at, rm, ci, REV) for ci, _ in est],
                "n_analysts": [None for _ in est],
            }

    # 분기
    qt = _pick_fn_table(tabs, "Net Quarter")
    quarter = None
    est_q = None
    if qt is not None:
        rm, act, est = _fn_rows(qt, "Net Quarter")
        ends = [qlabel(s) for _, s in act]
        quarter = {
            "ends": ends,
            "revenue": [val(qt, rm, ci, REV) for ci, _ in act],
            "operating_income": [val(qt, rm, ci, "영업이익") for ci, _ in act],
            "net_income": [val(qt, rm, ci, "당기순이익") for ci, _ in act],
            "diluted_eps": [val(qt, rm, ci, "EPS(원)", "num") for ci, _ in act],
            "last_end": (ends[-1] + "-01") if ends else None,
        }
        est = est[:2]
        if est:
            est_q = {
                "ends": [qlabel(s) for _, s in est],
                "eps_avg": [val(qt, rm, ci, "EPS(원)", "num") for ci, _ in est],
                "eps_low": [None for _ in est], "eps_high": [None for _ in est],
                "eps_yearago": [None for _ in est],
                "rev_avg": [val(qt, rm, ci, REV) for ci, _ in est],
                "n_analysts": [None for _ in est],
            }

    return {
        "ticker": disp, "yf": code6, "name": KR_NAMES.get(disp, disp),
        "currency": "KRW", "source": "FnGuide",
        "annual": annual, "quarter_actual": quarter,
        "estimates": {"annual": est_annual, "quarter": est_q,
                      "eps_ok": True, "rev_ok": True, "note": "", "eps_currency": "KRW"},
    }


def fetch_one(disp, sym):
    t = yf.Ticker(sym)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}
    ann = annual_block(t)
    q = quarter_actuals(t)
    last_fy_year = ann["years"][-1] if ann and ann["years"] else None
    last_q_end = q["last_end"] if q else None
    cur = info.get("financialCurrency") or info.get("currency") or "USD"
    last_eps = ann["diluted_eps"][-1] if (ann and ann["diluted_eps"]) else None
    last_rev = ann["revenue"][-1] if (ann and ann["revenue"]) else None
    est = estimates(t, last_fy_year, last_q_end, cur, last_eps, last_rev)
    return {
        "ticker": disp,
        "yf": sym,
        "name": info.get("shortName") or info.get("longName") or disp,
        "currency": cur,
        "source": "yfinance",
        "annual": ann,
        "quarter_actual": q,
        "estimates": est,
    }


def main():
    today = dt.date.today().isoformat()
    out = {}
    for disp, sym in STOCKS:
        try:
            is_kr = disp.strip().endswith(" KS")
            print(f"  · {disp} ({'FnGuide' if is_kr else sym}) ...", flush=True)
            out[disp] = fnguide(disp) if is_kr else fetch_one(disp, sym)
            time.sleep(0.6)
        except Exception as e:
            print(f"    ! {disp} 실패: {e}", flush=True)
    payload = {"as_of": today, "data": out}
    js = ("// 펀드매니저 탭 종목 재무(손익계산서+컨센서스) — fetch_fm_financials.py 생성. 큐레이션(수동 갱신).\n"
          "window.FM_FINANCIALS = " + json.dumps(payload, ensure_ascii=False, allow_nan=False) + ";\n")
    with open("fm-financials.js", "w", encoding="utf-8") as f:
        f.write(js)
    print(f"\n완료: {len(out)}개 종목 → fm-financials.js ({today})")


if __name__ == "__main__":
    main()
