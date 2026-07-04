"""
섹터분석 탭(sectors.html)용 시총·12M Forward PER 데이터 수집.

- sectors.html의 종목 티커를 파싱 → yfinance로 marketCap + forwardPE 조회
- 결과를 sector-quotes.js (window.SECTOR_QUOTES) 로 저장 → sectors.html이 로드해 칩에 표시
- 손실기업/추정 부재 시 forwardPE=None (프런트에서 '—' 표시)

사용법: python fetch_sector_quotes.py
의존성: yfinance (requirements.txt)
"""
import io, os, re, sys, json, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = Path(__file__).parent
SRC = HERE / "sectors.html"
OUT = HERE / "sector-quotes.js"

import yfinance as yf


def clean_ticker(raw: str) -> str:
    """t:'MU (비교)' -> 'MU', '005930.KS' -> '005930.KS'. 티커 형태만 통과."""
    tok = raw.strip().split()[0].strip()
    return tok if re.fullmatch(r"[A-Za-z0-9.\-]+", tok) else ""


def extract_tickers(html: str):
    seen, out = set(), []
    # (?<![A-Za-z]) : 'market:' 의 t: 오매칭 방지 (종목 객체의 t:'...' 만 매칭)
    for m in re.finditer(r"(?<![A-Za-z])t:\s*'([^']+)'", html):
        t = clean_ticker(m.group(1))
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def fetch_one(t: str):
    mc = fpe = cur = None
    for attempt in range(3):
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
            mc = info.get("marketCap")
            fpe = info.get("forwardPE")
            cur = info.get("currency")
            if not mc:  # fast_info 폴백(시총만)
                try:
                    fi = tk.fast_info
                    mc = getattr(fi, "market_cap", None) or (fi.get("market_cap") if hasattr(fi, "get") else None)
                    cur = cur or (getattr(fi, "currency", None))
                except Exception:
                    pass
            if mc:
                break
        except Exception:
            pass
        time.sleep(1.2)
    # forwardPE 정제: 비정상값(음수·과대) 컷
    if fpe is not None:
        try:
            fpe = float(fpe)
            if fpe <= 0 or fpe > 500:
                fpe = None
        except Exception:
            fpe = None
    return mc, fpe, cur


def main():
    html = SRC.read_text(encoding="utf-8")
    tickers = extract_tickers(html)
    print(f"티커 {len(tickers)}개 수집 시작…")
    data, ok, miss = {}, 0, 0
    for i, t in enumerate(tickers, 1):
        mc, fpe, cur = fetch_one(t)
        if mc:
            data[t] = {"mc": mc, "fpe": round(fpe, 2) if fpe else None, "cur": cur or ""}
            ok += 1
        else:
            data[t] = {"mc": None, "fpe": None, "cur": cur or ""}
            miss += 1
        if i % 20 == 0:
            print(f"  {i}/{len(tickers)} … (ok {ok}, miss {miss})")
        time.sleep(0.4)
    from datetime import datetime, timezone, timedelta
    kst = timezone(timedelta(hours=9))
    as_of = datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")
    payload = {"as_of": as_of, "source": "yfinance", "data": data}
    OUT.write_text(
        "window.SECTOR_QUOTES = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"완료: {OUT.name} 작성 (ok {ok} / miss {miss} / 총 {len(tickers)}) · {as_of}")


if __name__ == "__main__":
    main()
