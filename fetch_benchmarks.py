"""
시장 지수 YTD + 일일 수익률 수집 (KOSPI/KOSDAQ/S&P/NASDAQ/SOX/USDKRW)
- yfinance에서 작년 12월부터 오늘까지 종가 받아 YTD 계산
- 결과를 benchmarks.js로 저장 (평문 — 공개 시장 데이터)
"""
import json
import sys
import io
from datetime import date, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    sys.exit("필요: pip install yfinance pandas")

HERE = Path(__file__).parent
OUT = HERE / "benchmarks.js"

BENCHMARKS = [
    # (이름, yahoo 티커, 소수자리, 카테고리)
    # MSCI 글로벌 (최상단 우선)
    ("MSCI ACWI",        "ACWI",      2, "MSCI"),
    ("MSCI EM",          "EEM",       2, "MSCI"),
    # 한국
    ("KOSPI",            "^KS11",     0, "한국"),
    ("KOSDAQ",           "^KQ11",     2, "한국"),
    # 미국
    ("S&P 500",          "^GSPC",     2, "미국"),
    ("NASDAQ",           "^IXIC",     2, "미국"),
    ("필라델피아 반도체",  "^SOX",      2, "미국"),
    # 유럽
    ("STOXX 600",        "^STOXX",    2, "유럽"),
    # 아시아
    ("니케이 225",        "^N225",     0, "아시아"),
    ("상해종합",          "000001.SS", 2, "아시아"),
    # 환율
    ("USD/KRW",          "KRW=X",     2, "환율"),
    # 변동성·기타
    ("VIX",              "^VIX",      2, "변동성"),
    # VKOSPI는 Yahoo 안정 티커 없음 — Investing.com 스크래핑이나 KRX OpenAPI 필요 (별도)
]


def main():
    today = date.today()
    start = date(today.year - 1, 12, 15)  # 작년 12월 후반부터
    end = today + timedelta(days=1)

    out = {"as_of": today.isoformat(), "indices": []}
    print(f"=== 시장 지수 ({today}) ===")
    for name, ticker, decimals, category in BENCHMARKS:
        try:
            hist = yf.Ticker(ticker).history(
                start=start.isoformat(), end=end.isoformat(), auto_adjust=False
            )
            if hist.empty:
                print(f"  [miss] {name} ({ticker})")
                continue

            # YTD 기준: 올해 1월 1일 직전 마지막 거래일 종가
            this_year_start = None
            for i, ts in enumerate(hist.index):
                if ts.year >= today.year:
                    this_year_start = i
                    break
            # NaN-safe: 베이스라인 + 현재가 + 이전가를 NaN 건너뛰며 찾기
            closes = hist["Close"]
            # baseline: 올해 시작 직전 마지막 거래일 (NaN 아닌 첫 값 찾기 - 뒤에서 앞으로)
            baseline = None
            for j in range(max(0, (this_year_start or len(hist)) - 1), -1, -1):
                v = closes.iloc[j]
                if not pd.isna(v):
                    baseline = float(v)
                    break
            # current: 마지막 NaN 아닌 값
            current = None
            current_idx = None
            for j in range(len(closes) - 1, -1, -1):
                v = closes.iloc[j]
                if not pd.isna(v):
                    current = float(v)
                    current_idx = j
                    break
            if baseline is None or current is None:
                print(f"  [miss] {name} ({ticker}) — 유효 가격 없음")
                continue
            ytd_pct = (current / baseline - 1) * 100 if baseline > 0 else None

            # 직전 거래일 대비 (current 바로 앞 NaN 아닌 값)
            daily_pct = None
            if current_idx is not None and current_idx > 0:
                for j in range(current_idx - 1, -1, -1):
                    v = closes.iloc[j]
                    if not pd.isna(v):
                        prev = float(v)
                        if prev > 0:
                            daily_pct = (current / prev - 1) * 100
                        break

            asof = str(hist.index[current_idx].date()) if current_idx is not None else str(hist.index[-1].date())
            out["indices"].append({
                "name": name,
                "ticker": ticker,
                "category": category,
                "current": round(current, 4),
                "baseline": round(baseline, 4),
                "ytd_pct": round(ytd_pct, 4) if ytd_pct is not None else None,
                "daily_pct": round(daily_pct, 4) if daily_pct is not None else None,
                "as_of": asof,
                "decimals": decimals,
            })
            print(f"  [ok]  {name:18s} {ticker:10s} {current:>10.2f}  "
                  f"YTD {ytd_pct:+6.2f}%  Δ {daily_pct:+5.2f}% ({asof})")
        except Exception as e:
            print(f"  [err] {name} ({ticker}): {e}")

    OUT.write_text(
        "// 시장 지수 YTD/일일 수익률 (공개 데이터, 평문). fetch_benchmarks.py로 갱신.\n"
        f"window.BENCHMARKS = {json.dumps(out, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    print(f"\n저장: {OUT.name}  ({len(out['indices'])}개 지수)")


if __name__ == "__main__":
    main()
