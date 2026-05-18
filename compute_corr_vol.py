"""
포트폴리오 상관 반영 변동성 계산.

- 각 종목의 yfinance 일별 수익률로 종목 간 상관행렬 계산
- 종목별 σ는 portfolio-data의 v260/v90 사용 (Bloomberg 기준 유지)
- 지역별 + 전체 포트폴리오의 상관-반영 σ를 계산해
  portfolio-data.plain.js의 `correlation_vol` 키에 저장

σ_p² = Σᵢ Σⱼ wᵢ · wⱼ · σᵢ · σⱼ · ρᵢⱼ
  (지역 내 또는 전체 포트폴리오에서, 비중은 해당 그룹 내에서 정규화)
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
    import numpy as np
    import pandas as pd
except ImportError as e:
    sys.exit(f"필요 패키지: pip install yfinance numpy pandas ({e})")


HERE = Path(__file__).parent
PLAIN_PATH = HERE / "portfolio-data.plain.js"

MKT_SUFFIX = {
    "US": "", "KS": ".KS", "KQ": ".KQ", "GY": ".DE",
    "IM": ".MI", "LN": ".L", "FP": ".PA", "SW": ".SW",
    "NA": ".AS", "JP": ".T", "HK": ".HK", "AU": ".AX",
}


def to_yahoo_ticker(bbg):
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


def resolve_ticker(h):
    yt = to_yahoo_ticker(h.get("ticker"))
    if yt:
        return yt
    return to_yahoo_ticker(h.get("proxy_ticker", "")) or None


def load_data():
    text = PLAIN_PATH.read_text(encoding="utf-8")
    m = re.search(r"window\.PORTFOLIO_DATA\s*=\s*(\{.*?\n\});", text, re.DOTALL)
    if not m:
        raise RuntimeError("PORTFOLIO_DATA 블록 미발견")
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
    PLAIN_PATH.write_text(new_text, encoding="utf-8")


def compute_group_vol(group, corr_df, sigma_key):
    """group: [(holding, ticker)], 비중은 그룹 내에서 정규화"""
    if not group:
        return None, None
    wts = np.array([h.get("w") or 0 for h, _ in group], dtype=float)
    sigmas = np.array([h.get(sigma_key) or 0 for h, _ in group], dtype=float)
    tickers = [yt for _, yt in group]
    if wts.sum() <= 0:
        return None, None
    wts = wts / wts.sum()
    simple = float((sigmas * wts).sum())
    try:
        corr_sub = corr_df.loc[tickers, tickers].fillna(0).values
    except KeyError:
        return simple, simple
    cov = np.outer(sigmas, sigmas) * corr_sub
    var = float(wts @ cov @ wts)
    return simple, float(np.sqrt(max(var, 0)))


def main():
    print("=== 상관 반영 변동성 계산 시작 ===")
    text, data = load_data()
    holdings = data["holdings"]

    holding_tickers = []
    for h in holdings:
        yt = resolve_ticker(h)
        if yt and (h.get("w") or 0) > 0 and (h.get("v260") or 0) > 0:
            holding_tickers.append((h, yt))

    unique = sorted(set(t for _, t in holding_tickers))
    print(f"종목 {len(holding_tickers)}개 · 유니크 티커 {len(unique)}개")

    end = date.today()
    start = end - timedelta(days=420)
    print(f"yfinance 다운로드: {start} ~ {end}")
    prices = yf.download(
        unique,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=False, progress=False, group_by="ticker",
    )

    # 가용 종가 컬럼만 추출
    if isinstance(prices.columns, pd.MultiIndex):
        avail = [t for t in unique if t in prices.columns.get_level_values(0)]
        close = pd.DataFrame({t: prices[t]["Close"] for t in avail})
    else:
        close = pd.DataFrame({unique[0]: prices["Close"]})
    close = close.dropna(how="all")
    returns = close.pct_change().dropna(how="all")
    print(f"가용 거래일: {len(returns)}")

    # 260일/90일 윈도우 상관행렬
    corr_260 = returns.tail(260).corr()
    corr_90 = returns.tail(63).corr()

    REGIONS = ["한국", "미국", "유럽", "글로벌", "이머징"]
    out = {"regions": {}, "total": {}, "computed_at": end.isoformat(),
           "trading_days": int(len(returns)),
           "tickers_used": len(close.columns)}

    for r in REGIONS:
        rg = [(h, yt) for h, yt in holding_tickers if h["region"] == r]
        s260, c260 = compute_group_vol(rg, corr_260, "v260")
        s90,  c90  = compute_group_vol(rg, corr_90,  "v90")
        if s260 is not None:
            out["regions"][r] = {
                "simple_v260": round(s260, 2),
                "corr_v260":   round(c260, 2),
                "simple_v90":  round(s90,  2),
                "corr_v90":    round(c90,  2),
                "count": len(rg),
            }

    s260, c260 = compute_group_vol(holding_tickers, corr_260, "v260")
    s90,  c90  = compute_group_vol(holding_tickers, corr_90,  "v90")
    out["total"] = {
        "simple_v260": round(s260, 2),
        "corr_v260":   round(c260, 2),
        "simple_v90":  round(s90,  2),
        "corr_v90":    round(c90,  2),
        "count": len(holding_tickers),
    }

    data["correlation_vol"] = out
    save_data(text, data)

    # 표 출력
    print()
    print(f"{'구분':<8} | {'단순 260D':>9} {'상관 260D':>9} {'분산효과':>9} | {'단순 90D':>9} {'상관 90D':>9} {'분산효과':>9}")
    print("-" * 80)
    def row(label, v):
        d260 = (v['corr_v260'] / v['simple_v260'] - 1) * 100 if v['simple_v260'] else 0
        d90  = (v['corr_v90']  / v['simple_v90']  - 1) * 100 if v['simple_v90']  else 0
        print(f"{label:<8} | {v['simple_v260']:>9.2f} {v['corr_v260']:>9.2f} {d260:>+8.1f}% | {v['simple_v90']:>9.2f} {v['corr_v90']:>9.2f} {d90:>+8.1f}%")
    for r in REGIONS:
        if r in out["regions"]:
            row(r, out["regions"][r])
    print("-" * 80)
    row("전체", out["total"])
    print(f"\n저장: {PLAIN_PATH.name}  (key=correlation_vol, {len(returns)} 거래일 기준)")


if __name__ == "__main__":
    main()
