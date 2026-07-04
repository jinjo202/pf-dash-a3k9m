# -*- coding: utf-8 -*-
"""
펀드매니저 탭 — ETF factsheet(AUM·거래량·보수·벤치마크·발행주수·상장일) 수집.
- fm-data.js의 sectors[].etfs/kr_etfs + regions[].etfs + themes[].plays(type=etf) 전체 유니버스 대상.
- 미국 상장 ETF: yfinance .info (totalAssets/averageVolume/netExpenseRatio/fundInceptionDate/sharesOutstanding).
  벤치마크 지수명은 yfinance에 필드가 없어 BENCHMARK_MAP(수동 큐레이션)으로 보강.
- 한국 상장 ETF: 네이버금융 종목 페이지(시가총액=AUM 근사·상장주식수·상장일·펀드보수·자산운용사·거래량).
  기초지수 설명문에서 정규식으로 벤치마크명 best-effort 추출, 실패 시 BENCHMARK_MAP 폴백.
- fm-etf.js (window.FM_ETF) 생성. fm.html이 ETF칩 클릭 시 모달로 표시.

⚠ 큐레이션/수동 갱신 스크립트(cron 대상 아님). ETF 유니버스 추가 시 fm-data.js와 함께 재실행:
    python fetch_etf_factsheet.py
"""
import json
import re
import subprocess
import sys
import io
import datetime as dt

import requests
import yfinance as yf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# yfinance가 벤치마크(추종지수) 필드를 제공하지 않아 수동 보강 — fm-data.js ETF 유니버스 고정 세트.
BENCHMARK_MAP = {
    "SMH": "MVIS US Listed Semiconductor 25 Index", "SOXX": "ICE Semiconductor Index",
    "IGV": "ICE FactSet Software and IT Services Index", "XLK": "Technology Select Sector Index",
    "PAVE": "Indxx US Infrastructure Development Index", "ITA": "Dow Jones U.S. Select Aerospace & Defense Index",
    "XLI": "Industrial Select Sector Index", "XLV": "Health Care Select Sector Index",
    "IBB": "NASDAQ Biotechnology Index", "XLF": "Financial Select Sector Index",
    "XLC": "Communication Services Select Sector Index", "GDX": "NYSE Arca Gold Miners Index",
    "COPX": "Solactive Global Copper Miners Index", "XLE": "Energy Select Sector Index",
    "XLU": "Utilities Select Sector Index", "URA": "Solactive Global Uranium & Nuclear Components TR Index",
    "XLY": "Consumer Discretionary Select Sector Index", "XLP": "Consumer Staples Select Sector Index",
    "EWY": "MSCI Korea 25/50 Index", "RSP": "S&P 500 Equal Weight Index", "QQQ": "NASDAQ-100 Index",
    "IEMG": "MSCI Emerging Markets IMI", "VGK": "FTSE Developed Europe All Cap Index",
    "EWG": "MSCI Germany 25/50 Index", "DXJ": "WisdomTree Japan Hedged Equity Index",
    "MCHI": "MSCI China Index", "KWEB": "CSI Overseas China Internet Index",
    "INDA": "MSCI India Index", "EWT": "MSCI Taiwan 25/50 Index",
    "CIBR": "Nasdaq CTA Cybersecurity Index",
}


def load_fm_data():
    script = ("global.window={};eval(require('fs').readFileSync('fm-data.js','utf8'));"
              "process.stdout.write(JSON.stringify(window.FM_DATA||null));")
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError("fm-data.js 로드 실패: " + (proc.stderr or "")[:300])
    return json.loads(proc.stdout)


def etf_universe(fm):
    out, seen = [], set()

    def add(e, ctx):
        tk = e.get("ticker")
        if not tk or tk in seen:
            return
        seen.add(tk)
        out.append({"ticker": tk, "name": e.get("name"), "ctx": ctx})

    for s in (fm.get("sectors") or []):
        for e in (s.get("etfs") or []):
            add(e, "섹터:" + (s.get("name") or ""))
        for e in (s.get("kr_etfs") or []):
            add(e, "한국섹터:" + (s.get("name") or ""))
    for r in (fm.get("regions") or []):
        for e in (r.get("etfs") or []):
            add(e, "지역:" + (r.get("name") or ""))
    for t in (fm.get("themes") or []):
        for p in (t.get("plays") or []):
            if p.get("type") == "etf":
                add(p, "테마:" + (t.get("name") or ""))
    return out


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def compute_returns(yf_symbol):
    """yfinance 가격 히스토리로 1M/3M/YTD/1Y 수익률(%) 계산 — US·KR 공통(.KS 심볼).
    부진(언더퍼폼) 판별 데이터로 파이프라인에 주입된다. 실패 시 빈 dict."""
    try:
        h = yf.Ticker(yf_symbol).history(period="1y", auto_adjust=True)
    except Exception:
        return {}
    if h is None or h.empty:
        return {}
    c = h["Close"].dropna()
    if len(c) < 20:
        return {}
    cur = float(c.iloc[-1])

    def back(n):
        return round((cur / float(c.iloc[-n]) - 1) * 100, 1) if len(c) >= n else None

    ytd = None
    try:
        this_year = c.index.year == dt.date.today().year
        ys = c[this_year]
        if len(ys) > 1:
            ytd = round((cur / float(ys.iloc[0]) - 1) * 100, 1)
    except Exception:
        ytd = None
    return {"r_1m": back(21), "r_3m": back(63), "r_ytd": ytd, "r_1y": back(252)}


def us_etf(disp):
    t = yf.Ticker(disp)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}
    if not info or not info.get("totalAssets"):
        raise ValueError("yfinance info 비어있음")
    incep = info.get("fundInceptionDate")
    incep_iso = None
    if incep:
        try:
            incep_iso = dt.datetime.fromtimestamp(incep, dt.timezone.utc).date().isoformat()
        except Exception:
            incep_iso = None
    row = {
        "ticker": disp, "name": info.get("longName") or info.get("shortName") or disp,
        "market": "US", "currency": info.get("currency") or "USD",
        "price": info.get("regularMarketPrice") or info.get("navPrice"),
        "aum": info.get("totalAssets"),
        "volume_avg": info.get("averageVolume") or info.get("averageVolume10days"),
        "expense_ratio_pct": (info.get("netExpenseRatio") or info.get("annualReportExpenseRatio")),
        "benchmark": BENCHMARK_MAP.get(disp),
        "shares_outstanding": info.get("sharesOutstanding"),
        "inception_date": incep_iso,
        "issuer": info.get("fundFamily"),
        "category": info.get("category"),
        "yield_pct": (info.get("yield") * 100) if info.get("yield") is not None else None,
        "source": "yfinance",
    }
    row.update(compute_returns(disp))
    return row


_KR_PATTERNS = {
    "shares": re.compile(r'상장주식수</th>\s*<td><em>([\d,]+)</em>'),
    "list_date": re.compile(r'상장일</th>\s*<td>([^<]+)</td>'),
    "fee": re.compile(r'<td>연<em>([\d.]+)%</em>'),
    "manager": re.compile(r'자산운용사</th>\s*<td><span title="([^"]+)"'),
    "volume": re.compile(r'거래량\s*([\d,]+)</dd>'),
    "price": re.compile(r'no_today"[^>]*>\s*<em[^>]*>\s*<span class="blind">([\d,]+)</span>', re.S),
    "bench1": re.compile(r'기초지수인\s*(.+?지수)'),
    "bench2": re.compile(r'기초지수(?:는|인|로)?\s*[\'"“]?([A-Za-z0-9가-힣 &/·\-]+?지수)[\'"”]?[\s.,)]'),
}


def kr_etf(disp):
    code6 = disp.split()[0]
    r = requests.get("https://finance.naver.com/item/main.naver?code=" + code6,
                     headers=UA, timeout=15)
    r.encoding = r.apparent_encoding
    t = r.text

    m = re.search(r'id="_market_sum">(.*?)</td>', t, re.S)
    aum = None
    if m:
        seg = m.group(1)
        jo = re.search(r'(\d+)\s*조', seg)
        eok = re.search(r'([\d,]+)\s*(?:</em>)?\s*억원', seg)
        jo_v = int(jo.group(1)) if jo else 0
        eok_v = int(eok.group(1).replace(",", "")) if eok else 0
        if jo or eok:
            aum = (jo_v * 10000 + eok_v) * 1e8   # 억원 -> 원

    def find(key):
        m = _KR_PATTERNS[key].search(t)
        return m.group(1).strip() if m else None

    shares = find("shares")
    shares = int(shares.replace(",", "")) if shares else None
    volume = find("volume")
    volume = int(volume.replace(",", "")) if volume else None
    fee = find("fee")
    fee = float(fee) if fee else None
    list_date_raw = find("list_date")
    list_date_iso = None
    if list_date_raw:
        dm = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", list_date_raw)
        if dm:
            list_date_iso = "%s-%02d-%02d" % (dm.group(1), int(dm.group(2)), int(dm.group(3)))
    bench = find("bench1") or find("bench2") or BENCHMARK_MAP.get(disp)
    price = find("price")
    price = _num(price.replace(",", "")) if price else None

    row = {
        "ticker": disp, "name": disp, "market": "KR", "currency": "KRW",
        "price": price, "aum": aum, "volume_avg": volume,
        "expense_ratio_pct": fee, "benchmark": bench,
        "shares_outstanding": shares, "inception_date": list_date_iso,
        "issuer": find("manager"), "category": None, "yield_pct": None,
        "source": "NaverFinance",
    }
    row.update(compute_returns(code6 + ".KS"))   # 수익률은 yfinance(.KS)로
    return row


def load_prev():
    try:
        with open("fm-etf.js", encoding="utf-8") as f:
            m = re.search(r"window\.FM_ETF\s*=\s*(\{.*\})\s*;\s*$", f.read(), re.S)
        return ((json.loads(m.group(1)) or {}).get("data") or {}) if m else {}
    except Exception:
        return {}


def main():
    fm = load_fm_data()
    universe = etf_universe(fm)
    prev = load_prev()
    today = dt.date.today().isoformat()
    out = {}
    failed = []
    for e in universe:
        disp = e["ticker"]
        is_kr = disp.strip().endswith(" KS")
        try:
            print(f"  · {disp} ({'NaverFinance' if is_kr else 'yfinance'}) ...", flush=True)
            row = kr_etf(disp) if is_kr else us_etf(disp)
            if is_kr and e.get("name"):
                row["name"] = e.get("name")
            row["ctx"] = e.get("ctx")
            out[disp] = row
        except Exception as ex:
            print(f"    ! {disp} 실패: {ex}", flush=True)
            if disp in prev:
                out[disp] = prev[disp]
                out[disp]["stale"] = True
                print("      → 이전 데이터 유지(stale)", flush=True)
            failed.append(disp)
    if failed:
        print(f"\n⚠ 실패 {len(failed)}종목: {', '.join(failed)}", flush=True)
    payload = {"as_of": today, "data": out}
    js = ("// 펀드매니저 탭 ETF factsheet(AUM·거래량·보수·벤치마크·발행주수·상장일) — "
          "fetch_etf_factsheet.py 생성. 큐레이션(수동 갱신).\n"
          "window.FM_ETF = " + json.dumps(payload, ensure_ascii=False, allow_nan=False) + ";\n")
    with open("fm-etf.js", "w", encoding="utf-8") as f:
        f.write(js)
    print(f"\n완료: {len(out)}개 ETF → fm-etf.js ({today})")


if __name__ == "__main__":
    main()
