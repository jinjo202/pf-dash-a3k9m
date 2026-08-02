# -*- coding: utf-8 -*-
"""
fetch_kr_supply.py — 한국 증시 '기계적 수급' 지표 수집 → kr_supply.json

기존 kr_flows(외인/기관/개인 순매수)·kr_deposit(예탁금·신용잔고 잔액)이 못 잡는
레버리지·디레버리징 동학을 수치화한다. 2026-07 말 KOSPI -21% 급락 후 하루 +17.9%
반등(7/31)처럼, 방향성 수급이 아니라 **기계적 청산·숏커버**가 주도하는 국면을
CIO/브리핑이 근거를 갖고 서술할 수 있게 하는 것이 목적.

수집 항목
  1. 레버리지·인버스 ETF — 순자산(AUM)·거래대금·수익률
     · 롱/숏 거래대금 비율 = 레버리지 ÷ 인버스 (개인 방향성 베팅 쏠림)
     · 인버스 AUM 감소 + 지수 급등 = 숏커버 분출 프록시
  2. 신용융자 반대매매 위험 — 신용잔고 수준·변화 + 지수 낙폭 결합
     · 반대매매는 담보비율(통상 140%) 미달 시 강제청산 → 지수 급락 중
       신용잔고가 '급감'하면 이미 반대매매가 터진 것
  3. 숏커버 프록시 — KRX 공매도 잔고는 2025-12-27 로그인 전환으로 수집 불가.
     인버스 ETF 자금 동향 + 지수 반등 조합으로 대체(한계 명시).

소스
  · 네이버 ETF API(etfItemList.nhn) — 순자산·거래대금 스냅샷(무인증)
  · yfinance — ETF·지수 가격/거래량 히스토리(거래대금 = 종가×거래량, 백필 가능)
  · kr_deposit.json — 신용잔고·예탁금 시계열(fetch_kr_deposit.py 산출)

방어적: 개별 소스 실패는 해당 섹션만 생략하고 나머지는 생성. 전부 실패하면
기존 kr_supply.json을 보존하고 exit 1.
"""
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "kr_supply.json"
DEPOSIT = HERE / "kr_deposit.json"

NAVER_ETF = "https://finance.naver.com/api/sise/etfItemList.nhn"

# 추적 대상: 국내 지수 레버리지/인버스 중 유동성 상위. code → (표기명, 방향, 배율)
#   direction: "long"=레버리지(지수 상승 베팅), "short"=인버스(하락 베팅)
TRACKED = {
    "122630": ("KODEX 레버리지",            "long",  2.0),
    "233740": ("KODEX 코스닥150레버리지",    "long",  2.0),
    "252670": ("KODEX 200선물인버스2X",      "short", 2.0),
    "114800": ("KODEX 인버스",              "short", 1.0),
    "251340": ("KODEX 코스닥150선물인버스",  "short", 1.0),
}

INDEX = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}


def _get_json(url, referer):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": referer})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def naver_etf_snapshot():
    """{code: {aum_억, turnover_억, nav, price}} — 순자산은 네이버만 제공(yf에 없음)."""
    d = _get_json(NAVER_ETF, "https://finance.naver.com/sise/etf.naver")
    items = (d.get("result") or {}).get("etfItemList") or []
    out = {}
    for x in items:
        c = x.get("itemcode")
        if c in TRACKED:
            out[c] = {
                # marketSum=순자산총액(억원), amonut=거래대금(백만원 단위로 관측됨)
                "aum_억": x.get("marketSum"),
                "turnover_naver": x.get("amonut"),
                "price": x.get("nowVal"),
                "nav": x.get("nav"),
            }
    return out


def yf_history(days=260):
    """ETF·지수 히스토리. 거래대금(억) = 종가×거래량/1e8 — 백필 가능한 유일 경로."""
    import yfinance as yf
    hist = {}
    for code in TRACKED:
        try:
            h = yf.Ticker(f"{code}.KS").history(period=f"{days}d")
            if not h.empty:
                hist[code] = h
        except Exception as e:  # noqa: BLE001 — 개별 종목 실패는 전체를 막지 않음
            print(f"[warn] {code} 히스토리 실패: {type(e).__name__}: {e}")
    idx = {}
    for name, tk in INDEX.items():
        try:
            h = yf.Ticker(tk).history(period=f"{days}d")
            if not h.empty:
                idx[name] = h
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {name} 지수 실패: {type(e).__name__}: {e}")
    return hist, idx


def _pct(cur, prev):
    try:
        if prev in (None, 0):
            return None
        return round((cur / prev - 1) * 100, 2)
    except (TypeError, ZeroDivisionError):
        return None


def _turnover_억(h, i=-1):
    """i번째 행의 거래대금(억원) = 종가 × 거래량 / 1e8."""
    try:
        return round(float(h["Close"].iloc[i]) * float(h["Volume"].iloc[i]) / 1e8, 0)
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def build_etf(snap, hist):
    """레버리지/인버스 ETF 개별 지표 + 롱숏 거래대금 비율."""
    items, long_to, short_to, long_base, short_base = [], 0.0, 0.0, 0.0, 0.0
    trade_date = None
    for code, (name, direction, mult) in TRACKED.items():
        h = hist.get(code)
        row = {"code": code, "name": name, "direction": direction, "leverage": mult}
        row.update(snap.get(code) or {})
        if h is not None and len(h) >= 2:
            trade_date = trade_date or str(h.index[-1].date())
            c = h["Close"]
            row["r_1d"] = _pct(float(c.iloc[-1]), float(c.iloc[-2]))
            if len(c) >= 6:
                row["r_5d"] = _pct(float(c.iloc[-1]), float(c.iloc[-6]))
            to1 = _turnover_억(h)
            row["turnover_억"] = to1
            # 기준선은 반드시 '당일 제외' — 당일을 포함하면 스파이크가 자기 기준선을
            # 끌어올려 배율이 희석된다. 또 급락장은 직전 5일도 이미 폭증해 있어
            # 20일 평균을 주 기준선으로 쓴다(5일은 참고용).
            def _avg(lo, hi):
                v = [_turnover_억(h, -k) for k in range(lo, hi)]
                v = [x for x in v if x is not None]
                return sum(v) / len(v) if v else None
            base20, base5 = _avg(2, 22), _avg(2, 7)
            row["turnover_기준선20_억"] = round(base20, 0) if base20 else None
            row["turnover_기준선5_억"] = round(base5, 0) if base5 else None
            if to1 is not None and base20:
                row["turnover_대비기준선_배"] = round(to1 / base20, 2)
            if to1 is not None:
                if direction == "long":
                    long_to += to1
                else:
                    short_to += to1
            if base20:
                if direction == "long":
                    long_base += base20
                else:
                    short_base += base20
        items.append(row)

    out = {"trade_date": trade_date, "items": items,
           "레버리지_거래대금_억": round(long_to, 0) or None,
           "인버스_거래대금_억": round(short_to, 0) or None}
    if short_to > 0:
        out["롱숏_거래대금비율"] = round(long_to / short_to, 2)
    if short_base > 0:
        out["롱숏_거래대금비율_평시"] = round(long_base / short_base, 2)
    return out


def build_credit(idx):
    """신용잔고 기반 반대매매 압력. 지수 낙폭과 결합해야 의미가 생긴다."""
    try:
        dp = json.loads(DEPOSIT.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"[warn] kr_deposit.json 읽기 실패: {e}")
        return None
    cr, de = dp.get("credit") or {}, dp.get("deposit") or {}
    cv, cd = cr.get("values") or [], cr.get("dates") or []
    dv = de.get("values") or []
    if not cv:
        return None
    out = {
        "as_of": cd[-1] if cd else None,
        "신용잔고_조": cv[-1],
        "고객예탁금_조": dv[-1] if dv else None,
    }
    if len(cv) >= 6:
        out["신용잔고_1주변화_조"] = round(cv[-1] - cv[-6], 2)
    if len(cv) >= 21:
        out["신용잔고_1개월변화_조"] = round(cv[-1] - cv[-21], 2)
    if dv and dv[-1]:
        out["신용_예탁금_배율"] = round(cv[-1] / dv[-1], 3)

    # 지수 낙폭(고점 대비) — 반대매매는 '레벨'이 아니라 '급락+신용'의 조합에서 터진다
    ks = idx.get("KOSPI")
    if ks is not None and len(ks) >= 21:
        c = ks["Close"]
        peak = float(c.iloc[-21:].max())
        cur = float(c.iloc[-1])
        trough = float(c.iloc[-21:].min())
        out["KOSPI_1개월고점대비_%"] = _pct(cur, peak)
        out["KOSPI_1개월최대낙폭_%"] = _pct(trough, peak)

    # 신용잔고 공시는 T+2 — 급락 당일·직후가 아직 안 잡힐 수 있다(오판 방지용 명시)
    out["공시시차_주의"] = (
        "신용잔고는 영업일 기준 약 2일 지연 공시. 최근 급락 구간의 반대매매가 "
        "아직 반영되지 않았을 수 있으므로, 잔고가 안 줄었다고 '청산 없음'으로 "
        "단정하지 말 것.")
    return out


def build_shortcover(etf, idx):
    """숏커버 프록시. KRX 공매도 잔고 직접 수집이 막혀 대체 지표를 쓴다(한계 명시)."""
    out = {"한계": (
        "KRX 정보데이터시스템이 2025-12-27부터 로그인 필수로 전환되어 공매도 잔고·"
        "거래대금 직접 수집 불가. 아래는 인버스 ETF 자금·지수 반등 조합에 기반한 "
        "간접 추정이며, 실제 공매도 잔고와 다를 수 있다.")}
    inv = [i for i in etf.get("items", []) if i.get("direction") == "short"]
    if inv:
        r1 = [i["r_1d"] for i in inv if i.get("r_1d") is not None]
        if r1:
            out["인버스ETF_당일평균수익률_%"] = round(sum(r1) / len(r1), 2)
        to = [i for i in inv if i.get("turnover_억") and i.get("turnover_기준선20_억")]
        if to:
            ratio = sum(i["turnover_억"] for i in to) / sum(i["turnover_기준선20_억"] for i in to)
            out["인버스ETF_거래대금_대비평시_배"] = round(ratio, 2)
    ks = idx.get("KOSPI")
    if ks is not None and len(ks) >= 2:
        c = ks["Close"]
        out["KOSPI_당일_%"] = _pct(float(c.iloc[-1]), float(c.iloc[-2]))
    # 판정: 지수 급등 + 인버스 급락 + 인버스 거래대금 폭증 = 숏커버 분출 정황
    ks_up = (out.get("KOSPI_당일_%") or 0) >= 3
    inv_dn = (out.get("인버스ETF_당일평균수익률_%") or 0) <= -3
    vol_spike = (out.get("인버스ETF_거래대금_대비평시_배") or 0) >= 1.5
    if ks_up and inv_dn and vol_spike:
        out["정황"] = "숏커버 분출 정황 강함(지수 급등 + 인버스 급락 + 인버스 거래대금 폭증)"
    elif ks_up and inv_dn:
        out["정황"] = "숏커버 정황 보통(지수 급등 + 인버스 급락, 거래대금 확인 필요)"
    else:
        out["정황"] = "특이 정황 없음"
    return out


def main():
    snap, hist, idx = {}, {}, {}
    try:
        snap = naver_etf_snapshot()
        print(f"네이버 ETF 스냅샷: {len(snap)}종목")
    except Exception as e:  # noqa: BLE001 — AUM만 결측되고 나머지는 계속
        print(f"[warn] 네이버 ETF 실패(AUM 생략): {type(e).__name__}: {e}")
    try:
        hist, idx = yf_history()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] yfinance 실패: {type(e).__name__}: {e}")

    if not hist and not snap:
        print("[error] 모든 소스 실패 — 기존 kr_supply.json 보존")
        return 1

    etf = build_etf(snap, hist)
    payload = {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "naver ETF API(순자산) + yfinance(가격·거래량) + kr_deposit.json(신용)",
        "설명": "레버리지·인버스 ETF와 신용융자로 본 기계적 수급(디레버리징·숏커버) 지표",
        "leverage_etf": etf,
        "credit": build_credit(idx),
        "short_cover": build_shortcover(etf, idx),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"완료: {OUT}")
    print(f"  롱숏 거래대금비율: {etf.get('롱숏_거래대금비율')} "
          f"(평시 {etf.get('롱숏_거래대금비율_평시')})")
    print(f"  숏커버 정황: {(payload['short_cover'] or {}).get('정황')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
