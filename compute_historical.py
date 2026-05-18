"""
compute_historical.py — 포트폴리오 일별 mkt 시리즈 + MSCI ACWI 비교

YTD 기준 (장부가 시작값) 으로 각 종목의 일별 mkt 시리즈 계산:
  mkt_t = book × (price_t / price_year_start)

MSCI ACWI는 ACWI ETF로 대용 (지수 직접 티커 없음, 추적오차 < 0.1%/년).

결과는 portfolio-data.plain.js의 `historical` 키에 저장:
  - dates: ["2026-01-02", ...]
  - portfolio_total: [4912.18, ...]   # 억원
  - holdings_mkt: { "KODEX 200 ETF": [349.74, ...], ... }
  - acwi_normalized: [4912.18, ...]   # 포트폴리오 시작값에 정규화
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
    sys.exit("필요 패키지: pip install yfinance pandas")


HERE = Path(__file__).parent
PLAIN = HERE / "portfolio-data.plain.js"

MKT_SUFFIX = {
    "US": "", "KS": ".KS", "KQ": ".KQ", "GY": ".DE", "IM": ".MI",
    "LN": ".L", "FP": ".PA", "SW": ".SW", "NA": ".AS", "JP": ".T",
    "HK": ".HK", "AU": ".AX",
}


def to_yahoo(bbg):
    if not bbg:
        return None
    parts = bbg.strip().split()
    if len(parts) < 2:
        return None
    code, mkt = parts[0], parts[1].upper()
    suffix = MKT_SUFFIX.get(mkt)
    if suffix is None:
        return None
    if mkt == "KS" and not re.fullmatch(r"\d{6}", code):
        return None
    return code + suffix


def resolve(h):
    return to_yahoo(h.get("ticker")) or to_yahoo(h.get("proxy_ticker", ""))


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
    text, data = load_data()
    holdings = data["holdings"]
    today = date.today()
    year_start = date(today.year, 1, 1)
    fetch_start = year_start - timedelta(days=14)  # 연초 직전 거래일 확보용

    print(f"=== Historical 데이터 수집 ({year_start} ~ {today}) ===")

    # 각 holding의 yahoo ticker 매핑 (book > 0 인 것만)
    holding_tickers = []
    for h in holdings:
        yt = resolve(h)
        if yt and (h.get("book") or 0) > 0:
            holding_tickers.append((h, yt))

    unique = sorted(set(t for _, t in holding_tickers))
    fetch_list = unique + ["ACWI"]
    print(f"받을 티커: {len(unique)}개 + ACWI = {len(fetch_list)}개")

    prices = yf.download(
        fetch_list,
        start=fetch_start.isoformat(),
        end=(today + timedelta(days=1)).isoformat(),
        auto_adjust=False, progress=False, group_by="ticker",
    )

    if isinstance(prices.columns, pd.MultiIndex):
        avail = [t for t in fetch_list if t in prices.columns.get_level_values(0)]
        close = pd.DataFrame({t: prices[t]["Close"] for t in avail})
    else:
        close = pd.DataFrame({fetch_list[0]: prices["Close"]})
    close = close.dropna(how="all")
    if close.index.tz is not None:
        close.index = close.index.tz_localize(None)

    all_dates = sorted(close.index)
    # YTD 시작 = year_start 이후 첫 거래일
    ytd_idx = next((i for i, d in enumerate(all_dates) if d.date() >= year_start), None)
    if ytd_idx is None:
        print("YTD 시작일 못 찾음")
        return
    ytd_dates = all_dates[ytd_idx:]
    dates_str = [d.strftime("%Y-%m-%d") for d in ytd_dates]
    print(f"YTD 거래일: {len(dates_str)} ({dates_str[0]} ~ {dates_str[-1]})")

    holdings_mkt = {}
    portfolio_total = [0.0] * len(ytd_dates)

    for h, yt in holding_tickers:
        if yt not in close.columns:
            print(f"  [skip]  {h['name']} ({yt})")
            continue
        series = close[yt]
        # YTD 첫 거래일 가격
        ytd_start_price = None
        for d in ytd_dates:
            if d in series.index and not pd.isna(series.loc[d]):
                ytd_start_price = float(series.loc[d])
                break
        if not ytd_start_price or ytd_start_price <= 0:
            print(f"  [skip]  {h['name']} — YTD 시작가 없음")
            continue
        book = h.get("book") or 0
        # 일별 mkt 계산
        mkt_series = []
        last_price = ytd_start_price
        for d in ytd_dates:
            if d in series.index and not pd.isna(series.loc[d]):
                last_price = float(series.loc[d])
            # last_price 가 직전 가용 가격 (forward-fill)
            mkt_t = book * (last_price / ytd_start_price)
            mkt_series.append(round(mkt_t, 2))
        holdings_mkt[h["name"]] = mkt_series
        for i, v in enumerate(mkt_series):
            portfolio_total[i] += v
        ret = (mkt_series[-1] / book - 1) * 100
        print(f"  [ok]    {h['name']:42s} {yt:12s}  YTD {ret:+6.2f}%")

    # ACWI 정규화 — 포트폴리오 시작값에 맞춤
    acwi_normalized = None
    if "ACWI" in close.columns:
        acwi_series = close["ACWI"]
        acwi_start_price = None
        for d in ytd_dates:
            if d in acwi_series.index and not pd.isna(acwi_series.loc[d]):
                acwi_start_price = float(acwi_series.loc[d])
                break
        if acwi_start_price and acwi_start_price > 0:
            portfolio_start = portfolio_total[0] if portfolio_total[0] > 0 else 1
            acwi_normalized = []
            last_acwi = acwi_start_price
            for d in ytd_dates:
                if d in acwi_series.index and not pd.isna(acwi_series.loc[d]):
                    last_acwi = float(acwi_series.loc[d])
                acwi_normalized.append(round(portfolio_start * (last_acwi / acwi_start_price), 2))

    data["historical"] = {
        "from": dates_str[0],
        "to": dates_str[-1],
        "dates": dates_str,
        "portfolio_total": [round(v, 2) for v in portfolio_total],
        "holdings_mkt": holdings_mkt,
        "acwi_normalized": acwi_normalized,
        "computed_at": today.isoformat(),
    }
    save_data(text, data)

    # 요약 출력
    p0, pN = portfolio_total[0], portfolio_total[-1]
    p_ret = (pN / p0 - 1) * 100 if p0 > 0 else 0
    print("")
    print(f"포트폴리오 YTD: {p0:,.2f} → {pN:,.2f}  ({p_ret:+.2f}%)")
    if acwi_normalized:
        a0, aN = acwi_normalized[0], acwi_normalized[-1]
        a_ret = (aN / a0 - 1) * 100
        alpha = p_ret - a_ret
        print(f"ACWI    YTD:   {a0:,.2f} → {aN:,.2f}  ({a_ret:+.2f}%)")
        print(f"초과수익 (alpha): {alpha:+.2f}%p")
    print(f"\n저장: {PLAIN.name}  ({len(dates_str)} 거래일, {len(holdings_mkt)} 종목)")


if __name__ == "__main__":
    main()
