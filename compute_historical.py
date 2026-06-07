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


def resolve_with_fallback(h):
    """direct yahoo ticker + (있다면) proxy yahoo ticker 모두 반환"""
    direct = to_yahoo(h.get("ticker"))
    proxy = to_yahoo(h.get("proxy_ticker", ""))
    primary = direct or proxy
    fallback = (proxy if proxy and proxy != primary else None)
    return primary, fallback


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

    # 각 holding의 yahoo ticker 매핑 (book > 0 인 것만) — primary + fallback(proxy)
    holding_tickers = []  # [(holding, primary_yt, fallback_yt_or_None)]
    for h in holdings:
        primary, fallback = resolve_with_fallback(h)
        if primary and (h.get("book") or 0) > 0:
            holding_tickers.append((h, primary, fallback))

    # STOXX 600: ^STOXX는 YTD 시작 데이터 누락이 잦음 → IEUR(iShares Core MSCI Europe)
    #   ETF로 유럽 벤치마크를 안정적으로 추적 (지역 BM 비교용).
    BM_TICKERS = [("MSCI ACWI", "ACWI"), ("S&P 500", "^GSPC"), ("KOSPI", "^KS11"),
                  ("STOXX 600", "IEUR"), ("니케이 225", "EWJ"), ("MSCI EM", "EEM")]
    # 섹터 proxy ETF (US sector SPDRs)
    SECTOR_TICKERS = [("IT","XLK"), ("Communication","XLC"), ("Industrials","XLI"),
                      ("Materials","XLB"), ("Healthcare","XLV"), ("Cons Disc","XLY"),
                      ("Cons Staples","XLP"), ("Financials","XLF"), ("Energy","XLE"),
                      ("Utilities","XLU")]
    # primary + fallback 모두 fetch + FX
    unique = sorted(set([p for _, p, _ in holding_tickers] + [f for _, _, f in holding_tickers if f]))
    bm_yt = [t for _, t in BM_TICKERS]
    sec_yt = [t for _, t in SECTOR_TICKERS]
    fx_yt = ["KRW=X", "EURKRW=X"]  # USDKRW, EURKRW (share-aware mkt 계산용)
    fetch_list = sorted(set(unique + bm_yt + sec_yt + fx_yt))
    print(f"받을 티커: 종목 {len(unique)}개 + 지역BM {len(bm_yt)}개 + 섹터 {len(sec_yt)}개 + FX {len(fx_yt)}개")

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

    def get_ytd_start(yt):
        """주어진 티커의 YTD 시작 가격 (없으면 None)"""
        if yt not in close.columns:
            return None
        s = close[yt]
        for d in ytd_dates:
            if d in s.index and not pd.isna(s.loc[d]):
                return float(s.loc[d]), s
        return None

    # ── share-aware mkt 시리즈 ──────────────────────────────
    # 각 holding의 일별 mkt = (해당 시점 보유 shares) × close_price × FX
    # FX 시리즈 (USD/EUR → KRW). 없으면 day-of 값으로 forward-fill.
    def fx_series(yt, default):
        """KRW=X (=USDKRW) 같은 FX의 일별 값. 없으면 default (사용자가 추정한 평균값)."""
        if yt not in close.columns:
            return [default] * len(ytd_dates)
        s = close[yt]
        last = None
        out = []
        for d in ytd_dates:
            if d in s.index and not pd.isna(s.loc[d]):
                last = float(s.loc[d])
            out.append(last if last is not None else default)
        return out

    usdkrw = fx_series("KRW=X", 1450.0)   # USD→KRW 기본 ~1450
    eurkrw = fx_series("EURKRW=X", 1550.0)  # EUR→KRW 기본 ~1550

    def fx_for(ccy_or_isin, idx):
        """holding의 통화별 FX (1억 KRW = 1e8 KRW 단위 환산용)."""
        s = str(ccy_or_isin or "")
        if s.startswith("US") or s.startswith("XLK") or s.endswith(" "):
            return usdkrw[idx]
        if s.startswith("IE") or s.startswith("LU"):
            return eurkrw[idx]
        # XDAX / German tickers via fallback EWG (USD ETF) — USD
        return 1.0  # KR ticker — 환산 불필요

    # 거래를 isin별로 그룹화
    trades_by_isin = {}
    for t in data.get("trades", []):
        trades_by_isin.setdefault(t["isin"], []).append(t)
    for tt in trades_by_isin.values():
        tt.sort(key=lambda x: x["date"])

    for h, primary, fallback in holding_tickers:
        chosen_yt = primary
        result = get_ytd_start(primary)
        used_proxy = False
        if result is None and fallback:
            result = get_ytd_start(fallback)
            if result is not None:
                chosen_yt = fallback
                used_proxy = True

        if result is None:
            print(f"  [skip]  {h['name']:42s} (no YTD data for {primary}{' / ' + fallback if fallback else ''})")
            continue
        ytd_start_price, series = result

        # start_2026 = 1/1 시작가치 (12/31 시트 기준). 신규 종목은 0.
        # book은 이전 코드 호환용 — 신규 종목에서는 매수원가가 들어있어 share 계산에 부적합.
        start_2026 = h.get("start_2026")
        book = start_2026 if start_2026 is not None else (h.get("book") or 0)
        # FX 결정 (ticker 또는 ISIN로 통화 추정)
        isin = h.get("isin", "")
        ccy = "KRW"
        if isin.startswith("US"): ccy = "USD"
        elif isin.startswith("IE") or isin.startswith("LU"): ccy = "EUR"
        elif primary and not primary.endswith(".KS") and not primary.endswith(".KQ") and not primary.endswith(".DE"):
            ccy = "USD"  # XLK 같은 US ticker

        fx_arr = usdkrw if ccy == "USD" else (eurkrw if ccy == "EUR" else [1.0]*len(ytd_dates))

        # 1/1 시작 shares (start_2026 → shares)
        # start_value(억KRW) × 1e8 = KRW. shares = KRW / (price × FX)
        start_fx = fx_arr[0] if fx_arr else 1.0
        start_shares = (book * 1e8 / (ytd_start_price * start_fx)) if (book > 0 and ytd_start_price > 0) else 0.0

        # 이 holding의 매매 (isin 기준)
        my_trades = trades_by_isin.get(isin, [])

        mkt_series = []
        last_price = ytd_start_price
        for i, d in enumerate(ytd_dates):
            if d in series.index and not pd.isna(series.loc[d]):
                last_price = float(series.loc[d])
            d_str = d.strftime("%Y-%m-%d")
            # 이 날까지의 누적 share 변화
            shares = start_shares
            for t in my_trades:
                if t["date"] > d_str:
                    break
                tshares = t.get("shares")
                if tshares is None:
                    continue
                if t["action"] == "매입":
                    shares += tshares
                else:  # 매도
                    shares -= tshares
            mkt_t = shares * last_price * fx_arr[i] / 1e8
            mkt_series.append(round(max(mkt_t, 0), 2))
        holdings_mkt[h["name"]] = mkt_series
        for i, v in enumerate(mkt_series):
            portfolio_total[i] += v
        ret = (mkt_series[-1] / book - 1) * 100 if book > 0 else 0
        tag = "proxy" if used_proxy else "ok   "
        n_trades = len(my_trades)
        trade_note = f"  [trades:{n_trades}]" if n_trades else ""
        print(f"  [{tag}] {h['name']:42s} {chosen_yt:12s}  YTD {ret:+6.2f}%{trade_note}")

    # 벤치마크별 일별 종가 시리즈 (forward-fill, 정규화 X — 클라이언트에서 블렌드)
    benchmarks = {}
    for bm_name, bm_ticker in BM_TICKERS:
        if bm_ticker not in close.columns:
            print(f"  [skip BM] {bm_name} ({bm_ticker})")
            continue
        series = close[bm_ticker]
        last = None
        values = []
        for d in ytd_dates:
            if d in series.index and not pd.isna(series.loc[d]):
                last = float(series.loc[d])
            values.append(round(last, 4) if last else None)
        # 첫 값이 비어있으면 못 씀
        if values[0] is None:
            print(f"  [skip BM] {bm_name} — YTD 시작 데이터 없음")
            continue
        v0 = values[0]
        vN = values[-1]
        ret = (vN / v0 - 1) * 100
        print(f"  [BM ok] {bm_name:12s} {bm_ticker:8s}  YTD {ret:+6.2f}%")
        benchmarks[bm_name] = {
            "ticker": bm_ticker,
            "values": values,
            "ytd_return": round(ret, 4),
        }

    # 섹터 ETF YTD 수익률 (proxy for sector returns)
    sector_returns = {}
    for sec_name, sec_ticker in SECTOR_TICKERS:
        if sec_ticker not in close.columns:
            continue
        series = close[sec_ticker]
        v0 = None
        for d in ytd_dates:
            if d in series.index and not pd.isna(series.loc[d]):
                v0 = float(series.loc[d]); break
        vN = float(series.loc[ytd_dates[-1]]) if ytd_dates[-1] in series.index and not pd.isna(series.loc[ytd_dates[-1]]) else None
        if v0 and vN and v0 > 0:
            sector_returns[sec_name] = round((vN / v0 - 1) * 100, 4)
            print(f"  [Sec] {sec_name:14s} {sec_ticker:6s}  YTD {sector_returns[sec_name]:+6.2f}%")

    # 기존 attribution 메타 보존
    prev_hist = data.get("historical") or {}

    # sector_returns carry-forward: yfinance가 섹터 ETF 가격을 못 받으면 이번 계산이
    # 빈 dict가 되어 Brinson 섹터배분 효과가 전부 0으로 깨진다(2026-06-06 사고).
    # 직전 값과 merge — 이번에 받은 섹터만 갱신하고, 못 받은 섹터는 직전값 유지.
    prev_sr = prev_hist.get("sector_returns") or {}
    if len(sector_returns) < len(prev_sr):
        merged_sr = dict(prev_sr)
        merged_sr.update(sector_returns)  # 받은 값으로 덮어쓰고 나머지는 직전값
        print(f"  [carry-forward] sector_returns: 이번 {len(sector_returns)}개 수신 "
              f"→ 직전 {len(prev_sr)}개 보존(merge)")
        sector_returns = merged_sr

    data["historical"] = {
        "from": dates_str[0],
        "to": dates_str[-1],
        "dates": dates_str,
        "portfolio_total": [round(v, 2) for v in portfolio_total],
        "holdings_mkt": holdings_mkt,
        "benchmarks": benchmarks,
        "sector_returns": sector_returns,
        "acwi_sector_weights": prev_hist.get("acwi_sector_weights"),
        "sector_proxy_tickers": prev_hist.get("sector_proxy_tickers"),
        "computed_at": today.isoformat(),
    }
    save_data(text, data)

    # 요약 출력
    p0, pN = portfolio_total[0], portfolio_total[-1]
    p_ret = (pN / p0 - 1) * 100 if p0 > 0 else 0
    print("")
    print(f"포트폴리오 YTD: {p0:,.2f} → {pN:,.2f}  ({p_ret:+.2f}%)")
    for bm_name, bm_data in benchmarks.items():
        a_ret = bm_data["ytd_return"]
        print(f"  vs {bm_name:12s}: {a_ret:+6.2f}%   초과 {p_ret - a_ret:+6.2f}%p")
    print(f"\n저장: {PLAIN.name}  ({len(dates_str)} 거래일, {len(holdings_mkt)} 종목, {len(benchmarks)} 벤치마크)")


if __name__ == "__main__":
    main()
