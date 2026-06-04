# -*- coding: utf-8 -*-
"""
한국 시장 paragraph 끝에 붙일 삼성 3종(전자/화재/생명) 일간 등락률 문자열을 출력.

판단 순서:
  1. daily-data.js 의 korea region as_of 가 인자 as_of 와 다르면 → "한국 휴장"
  2. yfinance 로 005930.KS(전자), 000810.KS(화재), 032830.KS(생명) 의 as_of 일자
     종가/전일종가 비교. 데이터 없으면 → "한국 휴장".
  3. 가져왔으면 "전자 +X.X%, 화재 +Y.Y%, 생명 +Z.Z%" (하락은 △).

사용법:
  python get_samsung_trio.py <as_of YYYY-MM-DD> [daily-data.js 경로]
출력:
  stdout 한 줄. 괄호는 붙이지 않음(호출자가 (...) 로 감싸도록).
"""
import sys, os, re, json
from datetime import datetime, timedelta

# 기본 daily-data.js 경로: 이 스크립트(briefing/) 의 부모 디렉터리(repo 루트).
DEFAULT_DAILY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "daily-data.js")


def korea_closed_per_daily(daily_data_path, as_of):
    """daily-data.js 의 korea region as_of 가 as_of 와 다르면 True (한국 휴장)."""
    try:
        with open(daily_data_path, "r", encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"window\.DAILY\s*=\s*(\{.*\})\s*;?\s*$", text, re.S)
        if not m:
            return False
        daily = json.loads(m.group(1))
        regions = daily.get("regions") or []
        korea = next((r for r in regions if r.get("key") == "korea"), None) or {}
        kao = korea.get("as_of")
        if kao and kao != as_of:
            return True
    except Exception:
        return False
    return False


def fetch_trio_yf(as_of):
    try:
        import yfinance as yf
    except ImportError:
        return None  # 모듈 없음 → caller 가 한국 휴장 처리
    target = datetime.strptime(as_of, "%Y-%m-%d").date()
    tickers = [("전자", "005930.KS"), ("화재", "000810.KS"), ("생명", "032830.KS")]
    results = {}
    any_match = False
    for name, sym in tickers:
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
            any_match = True
        except Exception:
            results[name] = None
    if not any_match:
        return None
    out = []
    for name in ["전자", "화재", "생명"]:
        v = results.get(name)
        if v is None:
            out.append("%s N/A" % name)
        elif v >= 0:
            out.append("%s +%.1f%%" % (name, v))
        else:
            out.append("%s △%.1f%%" % (name, abs(v)))
    return ", ".join(out)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: get_samsung_trio.py <as_of YYYY-MM-DD> [daily-data.js path]\n")
        sys.exit(2)
    as_of = sys.argv[1]
    daily_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DAILY

    if korea_closed_per_daily(daily_path, as_of):
        sys.stdout.buffer.write("한국 휴장".encode("utf-8"))
        return

    trio = fetch_trio_yf(as_of)
    if trio is None:
        # 미래/휴장/네트워크 실패 등 — 보수적으로 한국 휴장 처리.
        sys.stdout.buffer.write("한국 휴장".encode("utf-8"))
        return
    sys.stdout.buffer.write(trio.encode("utf-8"))


if __name__ == "__main__":
    main()
