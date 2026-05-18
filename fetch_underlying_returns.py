"""
fetch_underlying_returns.py — 각 ETF 상위 5 구성종목의 YTD 수익률 수집

portfolio-data의 holdings[].top_holdings에서 등장하는 모든 underlying 종목명을
Yahoo 티커로 매핑한 뒤 yfinance로 일별 가격을 받아 YTD 수익률 계산.

결과는 portfolio-data.plain.js의 `underlying_ytd` (top-level dict)로 저장:
  { "삼성전자": {"ticker": "005930.KS", "ytd": 35.42, "as_of": "2026-05-19"}, ... }
"""
import json
import re
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
PLAIN = HERE / "portfolio-data.plain.js"

# 종목명 → Yahoo 티커 매핑 (수동 큐레이션)
NAME_TO_TICKER = {
    # ===== 한국 ETF의 underlying =====
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "LG에너지솔루션": "373220.KS",
    "삼성바이오로직스": "207940.KS",
    "현대차": "005380.KS",
    "기아": "000270.KS",
    "현대모비스": "012330.KS",
    "한온시스템": "018880.KS",
    "한국타이어앤테크놀로지": "161390.KS",
    "HLB": "028300.KQ",
    "알테오젠": "196170.KQ",
    "에코프로비엠": "247540.KQ",
    "에코프로": "086520.KQ",
    "리노공업": "058470.KQ",
    "셀트리온": "068270.KS",
    "에이비엘바이오": "298380.KQ",
    "HD현대일렉트릭": "267260.KS",
    "LS ELECTRIC": "010120.KS",
    "효성중공업": "298040.KS",
    "한국전력기술": "052690.KS",
    "두산에너빌리티": "034020.KS",
    "한국전력": "015760.KS",
    "한전KPS": "051600.KS",
    "우리기술": "032820.KQ",
    "한화에어로스페이스": "012450.KS",
    "한국항공우주": "047810.KS",
    "현대로템": "064350.KS",
    "LIG넥스원": "079550.KS",
    "한화시스템": "272210.KS",

    # ===== 미국 ETF의 underlying =====
    "Apple Inc": "AAPL",
    "Microsoft Corp": "MSFT",
    "Microsoft": "MSFT",
    "NVIDIA Corp": "NVDA",
    "NVIDIA": "NVDA",
    "Amazon.com Inc": "AMZN",
    "Amazon": "AMZN",
    "Meta Platforms Inc": "META",
    "Meta Platforms": "META",
    "Alphabet Inc Class A": "GOOGL",
    "Alphabet Inc Class C": "GOOG",
    "Alphabet Inc Class": "GOOGL",  # XLC 일부 표기
    "Broadcom Inc": "AVGO",
    "Tesla Inc": "TSLA",
    "Caterpillar Inc": "CAT",
    "GE Aerospace": "GE",
    "GE Vernova Inc": "GEV",
    "Linde PLC": "LIN",
    "Newmont Corp": "NEM",
    "Nucor Corp": "NUE",
    "Netflix Inc": "NFLX",
    "Walt Disney Co": "DIS",
    "Williams-Sonoma": "WSM",
    "Casey's General Stores": "CASY",
    "Reliance Inc": "RS",
    "WW Grainger": "GWW",
    "Carlisle Companies": "CSL",

    # ===== 유럽 / 글로벌 ETF의 underlying =====
    "ASML Holding NV": "ASML",
    "ASML Holding NV AD": "ASML",
    "Novartis AG Regist": "NVS",
    "AstraZeneca PLC": "AZN",
    "UniCredit SpA": "UCG.MI",
    "Intesa Sanpaolo": "ISP.MI",
    "Enel SpA": "ENEL.MI",
    "Shell PLC": "SHEL",
    "Shell PLC ADR (Rep": "SHEL",
    "TotalEnergies SE": "TTE",
    "Toyota Motor Corp": "TM",
    "HSBC Holdings PLC": "HSBC",
    "Taiwan Semiconduct": "TSM",
    "TSMC": "TSM",
    "Samsung Electronic": "005930.KS",
    "SK Hynix Inc": "000660.KS",
    "SAP": "SAP",
    "Siemens AG": "SIE.DE",
    "Allianz": "ALV.DE",
    "Deutsche Telekom": "DTE.DE",
    "Mercedes-Benz Group": "MBG.DE",
    "ABB": "ABBN.SW",
    # 추가 매핑
    "Tencent Holdings Ltd": "0700.HK",
    "Take-Two Interactive Software Inc": "TTWO",
    "Shell PLC ADR (Representing - Ordinary Shares)": "SHEL",
    "Samsung Electronics Co Ltd": "005930.KS",
    "Alphabet": "GOOGL",
    "Novartis AG Registered Shares": "NVS",
    "Freeport-McMoRan Inc": "FCX",
    "Banco Santander SA": "SAN.MC",
    "Boeing Co": "BA",
}


def load_data():
    text = PLAIN.read_text(encoding="utf-8")
    m = re.search(r"window\.PORTFOLIO_DATA\s*=\s*(\{.*?\n\});", text, re.DOTALL)
    obj = m.group(1)
    obj = re.sub(r"//[^\n]*", "", obj)
    obj = re.sub(r",(\s*[}\]])", r"\1", obj)
    return text, json.loads(obj)


def save_data(text, data):
    new_obj = json.dumps(data, ensure_ascii=False, indent=2)
    new_text = re.sub(
        r"window\.PORTFOLIO_DATA\s*=\s*\{.*?\n\};",
        f"window.PORTFOLIO_DATA = {new_obj};",
        text, count=1, flags=re.DOTALL,
    )
    PLAIN.write_text(new_text, encoding="utf-8")


def main():
    print("=== Underlying YTD 수익률 수집 ===")
    text, data = load_data()
    holdings = data["holdings"]

    # 모든 unique 이름 추출
    names = set()
    for h in holdings:
        for t in (h.get("top_holdings") or []):
            n = (t.get("name") or "").strip()
            if n:
                names.add(n)
    print(f"고유 underlying 이름: {len(names)}개")

    # 이름 → 티커 매핑
    name_to_yt = {}
    missing = []
    for n in names:
        yt = NAME_TO_TICKER.get(n)
        if yt:
            name_to_yt[n] = yt
        else:
            missing.append(n)

    if missing:
        print("\n  [매핑 누락]")
        for n in missing:
            print(f"    - {n}")
        print(f"  → 위 이름들은 fetch_underlying_returns.py의 NAME_TO_TICKER에 추가 필요\n")

    unique_tickers = sorted(set(name_to_yt.values()))
    print(f"고유 티커: {len(unique_tickers)}개 — yfinance 다운로드")

    today = date.today()
    year_start = date(today.year, 1, 1)
    start = year_start - timedelta(days=14)
    end = today + timedelta(days=1)

    prices = yf.download(
        unique_tickers,
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=False, progress=False, group_by="ticker",
    )

    if isinstance(prices.columns, pd.MultiIndex):
        avail = [t for t in unique_tickers if t in prices.columns.get_level_values(0)]
        close = pd.DataFrame({t: prices[t]["Close"] for t in avail})
    else:
        close = pd.DataFrame({unique_tickers[0]: prices["Close"]})
    close = close.dropna(how="all")
    if close.index.tz is not None:
        close.index = close.index.tz_localize(None)

    # YTD 첫 거래일 찾기
    all_dates = sorted(close.index)
    ytd_idx = next((i for i, d in enumerate(all_dates) if d.date() >= year_start), None)
    if ytd_idx is None:
        print("YTD 시작일 못 찾음")
        return
    ytd_first = all_dates[ytd_idx]
    ytd_last = all_dates[-1]
    print(f"YTD 범위: {ytd_first.date()} ~ {ytd_last.date()}")

    # 티커별 YTD 수익률 계산
    ticker_ytd = {}
    for yt in unique_tickers:
        if yt not in close.columns:
            continue
        series = close[yt]
        # YTD 시작 가격 (forward-fill)
        first_price = None
        for d in all_dates[ytd_idx:]:
            v = series.loc[d] if d in series.index else None
            if v is not None and not pd.isna(v):
                first_price = float(v)
                break
        last_price = float(series.loc[ytd_last]) if ytd_last in series.index and not pd.isna(series.loc[ytd_last]) else None
        if first_price and last_price and first_price > 0:
            ytd = (last_price / first_price - 1) * 100
            ticker_ytd[yt] = round(ytd, 4)

    print(f"\n티커별 YTD: {len(ticker_ytd)}개 수익률 계산")

    # 이름별 YTD 매핑
    underlying_ytd = {}
    for name, yt in name_to_yt.items():
        if yt in ticker_ytd:
            underlying_ytd[name] = {
                "ticker": yt,
                "ytd": ticker_ytd[yt],
                "as_of": str(ytd_last.date()),
            }

    print(f"이름별 YTD: {len(underlying_ytd)}개\n")

    # 종목별 상위 5 출력 (참고용)
    for name, info in sorted(underlying_ytd.items(), key=lambda x: x[1]["ytd"], reverse=True)[:10]:
        print(f"  +{info['ytd']:+7.2f}%  {name:30s} ({info['ticker']})")
    print("  ...")
    for name, info in sorted(underlying_ytd.items(), key=lambda x: x[1]["ytd"])[:5]:
        print(f"  {info['ytd']:+7.2f}%  {name:30s} ({info['ticker']})")

    data["underlying_ytd"] = underlying_ytd
    save_data(text, data)
    print(f"\n저장: {PLAIN.name}")


if __name__ == "__main__":
    main()
