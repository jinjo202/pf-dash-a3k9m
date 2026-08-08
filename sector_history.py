"""
GICS 섹터 기간 수익률 시계열 (sector-history.js) 생성.

daily.html 'GICS 섹터 움직임' 기간 탭(1D/1M/3M/YTD/기간설정)용 1년 일간 시계열.
- 미국: SPDR 섹터 ETF 종가 (일간 히트맵과 동일 기준, base=100 정규화)
- 유럽/중국/일본/한국: fetch_daily UNIVERSE 구성 종목 일간수익률의
  섹터 동일가중 평균을 누적한 지수 (base=100)
  (일간 히트맵의 '유니버스 구성 종목 섹터 평균'과 동일 방법론)

사용법: python sector_history.py [--force]
cron:  daily-update.yml — as_of가 오늘(KST)이면 skip (하루 8회 중복수집 방지)
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

from fetch_daily import UNIVERSE, US_SECTORS

HERE = Path(__file__).parent
OUT = HERE / "sector-history.js"

KST = timezone(timedelta(hours=9))

# 한국 실투자 섹터 ETF (매크로 탭 섹터 로테이션용 kr_etf 리전).
# GICS 동일가중(korea 리전)과 별개 — 실제 매매 가능한 ETF 단위 섹터 구분.
# 전 종목 yfinance 검증 완료(2026-08-08). 방산·조선은 2023년 상장이라 히스토리 짧음.
KR_SECTOR_ETFS = [
    ("091160.KS", "반도체",       "KODEX 반도체"),
    ("305720.KS", "2차전지",      "KODEX 2차전지산업"),
    ("091180.KS", "자동차",       "KODEX 자동차"),
    ("091170.KS", "은행",         "KODEX 은행"),
    ("102970.KS", "증권",         "KODEX 증권"),
    ("140700.KS", "보험",         "KODEX 보험"),
    ("143860.KS", "바이오",       "TIGER 헬스케어"),
    ("228790.KS", "화장품",       "TIGER 화장품"),
    ("227560.KS", "음식료·생활",  "TIGER 200 필수소비재"),
    ("228810.KS", "엔터·미디어",  "TIGER 미디어컨텐츠"),
    ("157490.KS", "인터넷·SW",    "TIGER 소프트웨어"),
    ("117460.KS", "에너지·화학",  "KODEX 에너지화학"),
    ("117680.KS", "철강",         "KODEX 철강"),
    ("117700.KS", "건설",         "KODEX 건설"),
    ("140710.KS", "운송",         "KODEX 운송"),
    ("228800.KS", "여행·레저",    "TIGER 여행레저"),
    ("449450.KS", "방산",         "PLUS K방산"),
    ("466920.KS", "조선",         "SOL 조선TOP3"),
]


def _kst_today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def already_today() -> bool:
    """sector-history.js의 as_of가 오늘(KST)이면 True."""
    if not OUT.exists():
        return False
    head = OUT.read_text(encoding="utf-8")[:300]
    m = re.search(r'"as_of":\s*"(\d{4}-\d{2}-\d{2})"', head)
    return bool(m) and m.group(1) == _kst_today()


def build_us(close, dates):
    """미국: SPDR 섹터 ETF 종가를 base=100으로 정규화."""
    series = {}
    for etf, name_ko, _ in US_SECTORS:
        if etf not in close.columns:
            continue
        s = close[etf].ffill()
        first = s.first_valid_index()
        if first is None:
            continue
        base = s.loc[first]
        vals = []
        for d in dates:
            v = s.loc[d]
            vals.append(round(float(v) / base * 100, 2) if v == v else None)
        series[name_ko] = vals
    return series


def build_region(close, tickers_by_sector):
    """비미국: 섹터 구성 종목 일간수익률 동일가중 평균 누적 (base=100)."""
    import pandas as pd

    all_t = [t for ts in tickers_by_sector.values() for t in ts]
    avail = [t for t in all_t if t in close.columns]
    sub = close[avail].dropna(how="all")
    dates = [d.strftime("%Y-%m-%d") for d in sub.index]
    # 상장폐지/IPO 대응: ffill 후 pct_change (첫 유효값 이전은 NaN 유지)
    rets = sub.ffill().pct_change()
    series = {}
    for sector, ts in tickers_by_sector.items():
        cols = [t for t in ts if t in sub.columns]
        if not cols:
            continue
        # 그날 데이터 있는 종목들 평균 (전부 NaN인 날은 0)
        mean_ret = rets[cols].mean(axis=1, skipna=True).fillna(0.0)
        idx = (1.0 + mean_ret).cumprod() * 100.0
        series[sector] = [round(float(v), 2) for v in idx]
    return dates, series


def main():
    if "--force" not in sys.argv and already_today():
        print("skip: sector-history 이미 오늘자 — 재수집 생략 (--force 로 강제)")
        return

    etf_tickers = [etf for etf, _, _ in US_SECTORS]
    kr_etf_tickers = [t for t, _, _ in KR_SECTOR_ETFS]
    uni_tickers = [t for region in UNIVERSE.values() for t, _, _ in region]
    all_tickers = list(dict.fromkeys(etf_tickers + kr_etf_tickers + uni_tickers))
    print(f"다운로드: {len(all_tickers)}개 티커 1년 종가...")
    df = yf.download(all_tickers, period="1y", interval="1d",
                     auto_adjust=True, progress=False, group_by="column")
    close = df["Close"] if "Close" in df.columns.get_level_values(0) else df

    regions = {}

    # 미국 (SPDR ETF)
    us_close = close[[t for t in etf_tickers if t in close.columns]].dropna(how="all")
    us_dates = [d.strftime("%Y-%m-%d") for d in us_close.index]
    regions["us"] = {"dates": us_dates, "series": build_us(close, us_close.index)}

    # 그 외 지역 (유니버스 동일가중)
    for key in ("europe", "china", "japan", "korea"):
        by_sector = {}
        for t, _, sector in UNIVERSE[key]:
            by_sector.setdefault(sector, []).append(t)
        dates, series = build_region(close, by_sector)
        regions[key] = {"dates": dates, "series": series}
        print(f"  {key}: {len(dates)}일 × {len(series)}섹터")
    print(f"  us: {len(us_dates)}일 × {len(regions['us']['series'])}섹터")

    # 한국 실투자 ETF 섹터 (kr_etf) — US와 동일하게 종가 base=100 정규화.
    # 각 ETF의 자기 첫 유효값 기준이라 상장 시점이 달라도 시리즈 앞쪽은 None으로 유지됨.
    kr_avail = [t for t in kr_etf_tickers if t in close.columns]
    kr_close = close[kr_avail].dropna(how="all")
    kr_dates = [d.strftime("%Y-%m-%d") for d in kr_close.index]
    kr_series = {}
    for tk, name_ko, etf_nm in KR_SECTOR_ETFS:
        if tk not in close.columns:
            continue
        sr = close[tk].ffill()
        first = sr.first_valid_index()
        if first is None:
            continue
        base = sr.loc[first]
        vals = []
        for d in kr_close.index:
            v = sr.loc[d]
            vals.append(round(float(v) / base * 100, 2) if v == v and d >= first else None)
        kr_series[name_ko] = vals
    regions["kr_etf"] = {"dates": kr_dates, "series": kr_series,
                          "etfs": {name: {"ticker": tk, "name": nm}
                                   for tk, name, nm in KR_SECTOR_ETFS if name in kr_series}}
    print(f"  kr_etf: {len(kr_dates)}일 × {len(kr_series)}섹터")

    payload = {
        "as_of": _kst_today(),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regions": regions,
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # NaN 방어: json.dumps는 NaN을 그대로 내보낼 수 있음 → 명시 검증
    if "NaN" in body or "Infinity" in body:
        raise SystemExit("NaN/Infinity 포함 — 데이터 오류, 저장 중단")
    OUT.write_text(
        "// GICS 섹터 기간 수익률 시계열 (공개 데이터, 평문). sector_history.py로 갱신.\n"
        "window.SECTOR_HISTORY = " + body + ";\n",
        encoding="utf-8",
    )
    print(f"저장: {OUT.name} ({OUT.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
