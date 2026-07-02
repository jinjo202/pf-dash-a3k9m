# -*- coding: utf-8 -*-
"""
한국 시장 paragraph 끝에 붙일 삼성 3종(전자/화재/생명) 일간 등락률 문자열을 출력.

소스 순서(안정성 우선):
  1. 네이버 금융 실시간(polling) — 최신 거래일이 as_of 와 같을 때만. 일간
     등락률(fluctuationsRatio)을 직접 사용. KR 시장에 안정적(throttle 적음).
  2. yfinance — 네이버가 as_of 와 불일치(과거 날짜 재발송 등)하거나 실패 시
     005930/000810/032830 의 as_of 종가 대비 전일종가로 계산.
  3. 둘 다 실패하면 → **빈 출력**. 절대 "한국 휴장"으로 단정하지 않는다
     (괄호 미주입). 휴장 서술은 브리핑 본문(RULES_ASIA)이 region.as_of 로
     판정한다 — 여기서 fetch 실패를 휴장으로 오판하던 버그가 있었음.

사용법:
  python get_samsung_trio.py <as_of YYYY-MM-DD> [daily-data.js 경로]
출력:
  stdout 한 줄. 괄호는 붙이지 않음(호출자가 (...) 로 감싸도록).
"""
import sys, os, re, json
import urllib.request
from datetime import datetime, timedelta

# 기본 daily-data.js 경로: 이 스크립트(briefing/) 의 부모 디렉터리(repo 루트).
DEFAULT_DAILY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "daily-data.js")


TRIO = [("전자", "005930"), ("화재", "000810"), ("생명", "032830")]


def _format_trio(results):
    """{name: pct or None} → "전자 +X.X%, 화재 △Y.Y%, ..." (하락 △). 전부 None 이면 None."""
    if not any(v is not None for v in results.values()):
        return None
    out = []
    for name, _ in TRIO:
        v = results.get(name)
        if v is None:
            out.append("%s N/A" % name)
        elif v >= 0:
            out.append("%s +%.1f%%" % (name, v))
        else:
            out.append("%s △%.1f%%" % (name, abs(v)))
    return ", ".join(out)


def fetch_trio_naver(as_of):
    """네이버 금융 실시간(polling) 일간 등락률. 최신 거래일이 as_of 와 같을 때만
    사용(과거 재발송이면 None → yfinance 폴백). 시세 못 받으면 None."""
    results = {}
    for name, code in TRIO:
        try:
            url = ("https://polling.finance.naver.com/api/realtime/"
                   "domestic/stock/" + code)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
            item = (json.loads(data).get("datas") or [None])[0]
            if not item:
                results[name] = None
                continue
            traded = (item.get("localTradedAt") or "")[:10]
            if traded and traded != as_of:
                # 최신 거래일이 기준일과 다름 → 네이버 실시간으론 부정확. 폴백.
                return None
            raw = item.get("fluctuationsRatioRaw", item.get("fluctuationsRatio"))
            results[name] = float(str(raw).replace(",", ""))
        except Exception:
            results[name] = None
    return _format_trio(results)


def fetch_trio_yf(as_of):
    """yfinance 로 as_of 종가 대비 전일종가 등락률. 과거 날짜·네이버 폴백용."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    target = datetime.strptime(as_of, "%Y-%m-%d").date()
    results = {}
    for name, code in TRIO:
        sym = code + ".KS"
        try:
            t = yf.Ticker(sym)
            hist = t.history(start=target - timedelta(days=14),
                             end=target + timedelta(days=2),
                             auto_adjust=False)
            if hist.empty:
                results[name] = None
                continue
            matched_pos = None
            for i, idx in enumerate(hist.index):
                if idx.date() == target:
                    matched_pos = i
                    break
            if matched_pos is None or matched_pos == 0:
                results[name] = None
                continue
            close = float(hist.iloc[matched_pos]["Close"])
            prev = float(hist.iloc[matched_pos - 1]["Close"])
            if prev == 0:
                results[name] = None
                continue
            results[name] = (close - prev) / prev * 100.0
        except Exception:
            results[name] = None
    return _format_trio(results)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: get_samsung_trio.py <as_of YYYY-MM-DD> [daily-data.js path]\n")
        sys.exit(2)
    as_of = sys.argv[1]

    # 1차: 안정적 네이버(당일). 2차: yfinance(과거 재발송·폴백).
    trio = fetch_trio_naver(as_of) or fetch_trio_yf(as_of)
    # 둘 다 실패하면 빈 출력 — 절대 "한국 휴장"으로 단정하지 않는다.
    # (휴장 서술은 브리핑 본문 RULES_ASIA 가 region.as_of 로 판정.)
    if trio is None:
        return
    sys.stdout.buffer.write(trio.encode("utf-8"))


if __name__ == "__main__":
    main()
