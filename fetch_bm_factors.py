# -*- coding: utf-8 -*-
"""
fetch_bm_factors.py — 벤치마크 팩터 집계(bm-factors.js) 생성

벤치마크 구성종목을 직접 스크랩하는 대신, 각 지수를 추종하는 **프록시 ETF의
공시 집계지표**(Morningstar via yfinance funds_data.equity_holdings)를 사용한다.
iShares CSV 엔드포인트는 봇 차단이 있어 신뢰 불가 — 이 경로가 견고하다.

- Price/Earnings 등은 역수(수익률 yield) 형태로 오므로 1/x 변환.
- ROE는 항등식 ROE = (E/P)/(B/P) 로 도출 (E/B).
- 모멘텀·변동성은 클라이언트가 지수 가격 히스토리로 직접 계산(여기선 불필요).

출력: bm-factors.js → window.BM_FACTORS = { as_of, indices: {지수명: {pe, pb, roe, proxy}} }

cron 비용 절감: 기존 bm-factors.js가 3일 이내면 스킵(--force로 무시).
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bm-factors.js")

# 지수명(portfolio.html benchmarkState 키와 일치) → 프록시 ETF
PROXIES = {
    "MSCI ACWI": "ACWI",   # iShares MSCI ACWI ETF
    "S&P 500":   "IVV",    # iShares Core S&P 500 ETF
    "KOSPI":     "EWY",    # iShares MSCI South Korea ETF (KOSPI 대용)
}

FRESH_DAYS = 3


def fresh_enough(path: str) -> bool:
    try:
        age = time.time() - os.path.getmtime(path)
        return age < FRESH_DAYS * 86400
    except OSError:
        return False


def inv(x):
    """Morningstar 역수 지표 → 배수. 0/None 가드."""
    try:
        x = float(x)
        return round(1.0 / x, 2) if x > 1e-9 else None
    except (TypeError, ValueError):
        return None


def fetch_one(etf: str):
    import yfinance as yf
    fd = yf.Ticker(etf).funds_data
    eh = fd.equity_holdings  # DataFrame index: Price/Earnings 등, col: ETF심볼
    col = eh[etf] if etf in eh.columns else eh.iloc[:, 0]
    ep = col.get("Price/Earnings")   # E/P (yield 형태)
    bp = col.get("Price/Book")       # B/P
    pe = inv(ep)
    pb = inv(bp)
    roe = None
    try:
        ep_f, bp_f = float(ep), float(bp)
        if bp_f > 1e-9:
            roe = round(ep_f / bp_f * 100.0, 2)   # ROE% = (E/P)/(B/P)
    except (TypeError, ValueError):
        pass
    return {"pe": pe, "pb": pb, "roe": roe, "proxy": etf}


def main():
    force = "--force" in sys.argv
    if not force and fresh_enough(OUT):
        print(f"bm-factors.js가 {FRESH_DAYS}일 이내로 신선 — 스킵 (--force로 강제)")
        return 0

    indices = {}
    for name, etf in PROXIES.items():
        try:
            d = fetch_one(etf)
            if d["pe"] is None and d["roe"] is None:
                print(f"[warn] {name}({etf}): 집계지표 없음 — 제외")
                continue
            indices[name] = d
            print(f"{name}({etf}): PE={d['pe']} PB={d['pb']} ROE={d['roe']}%")
        except Exception as e:  # noqa: BLE001 — 개별 실패는 다른 지수에 영향 X
            print(f"[warn] {name}({etf}) 실패: {type(e).__name__}: {e}")

    if not indices:
        print("[error] 모든 프록시 실패 — 기존 파일 유지")
        return 1

    payload = {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "Morningstar fund aggregates via yfinance funds_data (proxy ETF)",
        "indices": indices,
    }
    js = ("// 벤치마크 팩터 집계 (자동생성: fetch_bm_factors.py — 수동편집 금지)\n"
          "// 프록시 ETF의 Morningstar 집계지표. ROE=(E/P)/(B/P) 도출.\n"
          "window.BM_FACTORS = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"완료: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
