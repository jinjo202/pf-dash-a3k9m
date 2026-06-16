# -*- coding: utf-8 -*-
"""
지수 일간 등락률 독립 교차검증 헬퍼.

fetch_daily.py(yfinance)가 한 거래일을 누락하면 등락률(chgPct)이 2거래일 누적으로
부풀려진다(2026-06-16 아시아 브리핑 사고: 코스피 +7.42% 게시 → 실제 +2.11%).
이 스크립트는 eastmoney/네이버에서 직전 2거래일 종가를 받아 '진짜' 일간 등락률을
계산하고, daily-data.js 의 chgPct 와 비교해 임계치(기본 0.3%p) 이상 차이나는 지수를
[MISMATCH] 로 표시한다. 브리핑 작성 전 반드시 실행해, 지수 통계 라인과 특징주 수치를
이 검증값 기준으로 보정할 것.

사용법:
  python verify_indices.py asia      # 닛케이·코스피·코스닥·상해·선전·항셍·H주
  python verify_indices.py us        # S&P500·나스닥·다우·유로스톡스50
출력: 사람이 읽는 표 + 마지막 줄에 JSON(자동 파싱용).
"""
import sys, json, urllib.request, urllib.error, time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UA = {"User-Agent": "Mozilla/5.0"}

def _get(url, timeout=15):
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
        except Exception as e:
            last = e; time.sleep(1.5)
    raise last

def eastmoney(secid, beg, end):
    """eastmoney 일봉. returns [(yyyy-mm-dd, close), ...] or []"""
    url = ("http://push2his.eastmoney.com/api/qt/stock/kline/get?secid=%s"
           "&fields1=f1&fields2=f51,f53&klt=101&fqt=0&beg=%s&end=%s" % (secid, beg, end))
    d = json.loads(_get(url))
    data = d.get("data")
    if not data:
        return []
    out = []
    for k in data.get("klines", []):
        ds, cs = k.split(",")[:2]
        out.append((ds, float(cs)))
    return out

def naver_world(symbol):
    """api.stock.naver.com 세계지수. returns [(yyyy-mm-dd, close)...] newest first."""
    url = "https://api.stock.naver.com/index/%s/price?pageSize=8&page=1" % symbol
    d = json.loads(_get(url))
    out = []
    for row in d:
        ds = (row.get("localTradedAt") or "")[:10]
        cs = float(str(row.get("closePrice")).replace(",", ""))
        out.append((ds, cs))
    return out

def naver_kr(symbol):
    """api.finance.naver.com siseJson. symbol=KOSPI/KOSDAQ or 6-digit code."""
    import re
    url = ("https://api.finance.naver.com/siseJson.naver?symbol=%s&requestType=1"
           "&startTime=20260601&endTime=20991231&timeframe=day" % symbol)
    req = urllib.request.Request(url, headers={**UA, "Referer": "https://finance.naver.com/"})
    raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
    rows = re.findall(r'\["(\d{8})",[^,]+,[^,]+,[^,]+,\s*([0-9.]+)', raw)
    return [("%s-%s-%s" % (d[:4], d[4:6], d[6:]), float(c)) for d, c in rows]

# 지역별 지수 정의: (key, 표시명, fetcher, 식별자, daily-data 매칭명)
ASIA = [
    ("nikkei", "닛케이225", "em", "100.N225", "닛케이 225"),
    ("kospi",  "코스피",     "em", "100.KS11", "KOSPI"),
    ("kosdaq", "코스닥",     "nkr", "KOSDAQ",  "KOSDAQ"),
    ("sse",    "상해종합",   "em", "1.000001", "상해 종합"),
    ("szse",   "선전성분",   "em", "0.399001", "선전 성분"),
    ("hsi",    "항셍",       "em", "100.HSI",  "항셍"),
    ("hscei",  "H주",        "em", "100.HSCEI","H주 지수"),
]
US = [
    ("spx",    "S&P500",     "em", "100.SPX",  "S&P 500"),
    ("ixic",   "나스닥",     "nw", ".IXIC",    "NASDAQ"),
    ("dji",    "다우",       "em", "100.DJIA", "다우"),
    ("sx5e",   "유로스톡스50","em","100.SX5E", "Euro Stoxx 50"),
]

def fetch_series(kind, ident):
    if kind == "em":
        return eastmoney(ident, "20260601", "20260701")
    if kind == "nw":
        s = naver_world(ident); s.sort(key=lambda x: x[0]); return s
    if kind == "nkr":
        return naver_kr(ident)
    return []

def load_daily_chg():
    """daily-data.js 의 {지수명: chgPct} 매핑."""
    try:
        t = open("daily-data.js", encoding="utf-8").read()
        d = json.loads(t[t.index("{"):].rstrip().rstrip(";"))
        out = {}
        for r in d["regions"]:
            for i in r.get("indices", []):
                out[i.get("name")] = i.get("chgPct")
        return out
    except Exception:
        return {}

def main():
    region = (sys.argv[1] if len(sys.argv) > 1 else "asia").lower()
    indices = ASIA if region == "asia" else US
    daily = load_daily_chg()
    result = {}
    print("지수 일간 등락 교차검증 (%s) — 독립 소스: eastmoney/네이버" % region)
    print("%-10s %12s %12s %10s %10s  %s" % ("지수", "직전종가", "당일종가", "검증등락", "daily-data", "판정"))
    for key, name, kind, ident, dname in indices:
        try:
            s = fetch_series(kind, ident)
            s = [(d, c) for d, c in s if c]
            if len(s) < 2:
                print("%-10s  데이터부족" % name); result[key] = None; continue
            (pd, pc), (ld, lc) = s[-2], s[-1]
            dp = (lc / pc - 1) * 100
            dd = daily.get(dname)
            flag = ""
            if dd is not None:
                flag = "[MISMATCH]" if abs(dd - dp) > 0.3 else "[OK]"
            print("%-10s %12.2f %12.2f %+9.2f%% %10s  %s"
                  % (name, pc, lc, dp, ("%+.2f%%" % dd if dd is not None else "-"), flag))
            result[key] = {"name": name, "prev_date": pd, "prev_close": round(pc, 2),
                           "last_date": ld, "last_close": round(lc, 2),
                           "daily_pct": round(dp, 2),
                           "daily_data_chgPct": dd,
                           "mismatch": (dd is not None and abs(dd - dp) > 0.3)}
        except Exception as e:
            print("%-10s  ERROR %s" % (name, type(e).__name__)); result[key] = None
    print("JSON:" + json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
