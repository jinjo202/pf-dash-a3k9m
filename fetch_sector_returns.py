"""
섹터·종목 수익률 산출 → sector-returns.js (sectors.html용)

- sectors.html의 DATA 블록에서 티커를 자동 추출(테마별)하여 동기화 유지.
- yfinance로 1년치 일별 종가를 받아 1M/3M/YTD 수익률 계산.
- 벤치마크: KOSPI(^KS11), S&P500(^GSPC). 초과성과는 프런트에서 종목 지역에 맞춰 계산.
- 섹터 '대표'는 해당 테마 구성종목의 동일가중(equal-weight) 바스켓 수익률.
- 출력: window.SECTOR_RETURNS = { as_of, benchmarks, stocks, themes }

사용법:  python fetch_sector_returns.py
"""
import re
import json
import sys
import io
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = Path(__file__).parent
SRC = HERE / "sectors.html"
OUT = HERE / "sector-returns.js"

BENCH = {"KOSPI": "^KS11", "SP500": "^GSPC"}


def parse_themes(html: str):
    """sectors.html의 DATA 블록에서 (theme_id -> [정규화 티커]) 추출."""
    start = html.index("var DATA")
    end = html.index("/* ===", start)
    block = html[start:end]
    themes = []  # [(id, [tickers])]
    cur = None
    for m in re.finditer(r"id:'([a-z0-9-]+)'|t:'([^']+)'", block):
        tid, tk = m.group(1), m.group(2)
        if tid:
            cur = {"id": tid, "tickers": []}
            themes.append(cur)
        elif tk and cur is not None:
            norm = tk.split()[0].strip()          # 'MU (비교)' -> 'MU'
            if norm and norm not in cur["tickers"]:
                cur["tickers"].append(norm)
    return themes


def rets_from_series(s: pd.Series):
    s = s.dropna()
    if len(s) < 2:
        return None
    last = float(s.iloc[-1])
    last_dt = s.index[-1]

    def back(days):
        cut = last_dt - pd.Timedelta(days=days)
        prior = s[s.index <= cut]
        if not len(prior):
            return None
        return round((last / float(prior.iloc[-1]) - 1) * 100, 1)

    # YTD: 전년도 마지막 종가 기준(없으면 올해 첫 종가)
    yr = last_dt.year
    prev = s[s.index < pd.Timestamp(yr, 1, 1)]
    base = float(prev.iloc[-1]) if len(prev) else float(s.iloc[0])
    ytd = round((last / base - 1) * 100, 1) if base else None
    return {"r1m": back(30), "r3m": back(91), "ytd": ytd}


def main():
    html = SRC.read_text(encoding="utf-8")
    themes = parse_themes(html)

    tickers = sorted({t for th in themes for t in th["tickers"]})
    universe = tickers + list(BENCH.values())
    print(f"종목 {len(tickers)}개 + 벤치마크 {len(BENCH)}개 다운로드…")

    raw = yf.download(universe, period="1y", interval="1d",
                      progress=False, auto_adjust=True)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if isinstance(close, pd.Series):
        close = close.to_frame()

    as_of = str(close.dropna(how="all").index[-1].date())

    stocks = {}
    missing = []
    for t in tickers:
        r = rets_from_series(close[t]) if t in close.columns else None
        if r is None:
            missing.append(t)
            continue
        stocks[t] = r

    benchmarks = {}
    for name, tk in BENCH.items():
        r = rets_from_series(close[tk]) if tk in close.columns else None
        benchmarks[name] = r or {"r1m": None, "r3m": None, "ytd": None}

    # 테마별 동일가중 바스켓
    theme_out = {}
    for th in themes:
        rows = [stocks[t] for t in th["tickers"] if t in stocks]
        if not rows:
            continue
        def avg(key):
            vals = [x[key] for x in rows if x.get(key) is not None]
            return round(sum(vals) / len(vals), 1) if vals else None
        theme_out[th["id"]] = {"r1m": avg("r1m"), "r3m": avg("r3m"),
                               "ytd": avg("ytd"), "n": len(rows)}

    payload = {"as_of": as_of, "benchmarks": benchmarks,
               "stocks": stocks, "themes": theme_out}
    body = ("// 자동 생성: fetch_sector_returns.py — 직접 편집 금지\n"
            "window.SECTOR_RETURNS = " + json.dumps(payload, ensure_ascii=False) + ";\n")
    OUT.write_text(body, encoding="utf-8")

    print(f"기준일 {as_of} · 종목 {len(stocks)}개 · 테마 {len(theme_out)}개 → {OUT.name}")
    if missing:
        print("데이터 없음(스킵):", ", ".join(missing))


if __name__ == "__main__":
    main()
