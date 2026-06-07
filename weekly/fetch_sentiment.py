# -*- coding: utf-8 -*-
"""
주간회의자료용 시장 센티먼트 지표 수집.

  - CNN Fear & Greed Index (지수 + 7개 구성요소, dataviz 엔드포인트)
  - AAII Investor Sentiment Survey (Bullish/Neutral/Bearish + Bull-Bear Spread)

둘 다 무료·공개 소스. 실패 시 해당 항목은 None 으로 두고 계속 진행.

사용법:
  python fetch_sentiment.py            # JSON 한 덩어리 stdout 출력
"""
import sys, io, json, re, ssl, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_CTX = ssl.create_default_context()


def _get(url, headers=None, timeout=25):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()


def get_cnn_fng():
    """CNN Fear & Greed Index. 반환: dict 또는 None."""
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    hdr = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://edition.cnn.com/markets/fear-and-greed",
        "Origin": "https://edition.cnn.com",
    }
    try:
        d = json.loads(_get(url, hdr).decode("utf-8", "replace"))
    except Exception as e:
        sys.stderr.write("CNN F&G fail: %s\n" % e)
        return None
    fg = d.get("fear_and_greed") or {}
    comp_keys = [
        ("market_momentum_sp125", "시장 모멘텀(S&P125)"),
        ("stock_price_strength", "주가 강도"),
        ("stock_price_breadth", "주가 폭(breadth)"),
        ("put_call_options", "풋/콜 옵션"),
        ("market_volatility_vix", "변동성(VIX)"),
        ("safe_haven_demand", "안전자산 수요"),
        ("junk_bond_demand", "정크본드 수요"),
    ]
    components = []
    for key, label in comp_keys:
        c = d.get(key) or {}
        if c.get("score") is not None:
            components.append({"label": label,
                               "score": round(float(c.get("score")), 1),
                               "rating": c.get("rating")})
    return {
        "score": round(float(fg.get("score", 0)), 1) if fg.get("score") is not None else None,
        "rating": fg.get("rating"),
        "prev_close": _r(fg.get("previous_close")),
        "prev_1week": _r(fg.get("previous_1_week")),
        "prev_1month": _r(fg.get("previous_1_month")),
        "prev_1year": _r(fg.get("previous_1_year")),
        "components": components,
    }


def _r(v):
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def get_aaii():
    """AAII Investor Sentiment Survey 최신치 + 직전주. 반환: dict 또는 None."""
    url = "https://www.aaii.com/sentimentsurvey"
    try:
        html = _get(url).decode("utf-8", "replace")
    except Exception as e:
        sys.stderr.write("AAII fail: %s\n" % e)
        return None
    pat = re.compile(
        r'\{\s*"date_":\s*"([0-9-]+)",.*?"bullish":\s*"([0-9.]+)",\s*'
        r'"bearish":\s*"([0-9.]+)",\s*"neutral":\s*"([0-9.]+)",\s*'
        r'spread:\s*"(-?[0-9.]+)"', re.S)
    rows = pat.findall(html)
    if not rows:
        sys.stderr.write("AAII parse: no series rows\n")
        return None
    rows.sort(key=lambda r: r[0])
    def mk(r):
        return {"date": r[0], "bullish": float(r[1]), "bearish": float(r[2]),
                "neutral": float(r[3]), "spread": float(r[4])}
    latest = mk(rows[-1])
    prev = mk(rows[-2]) if len(rows) > 1 else None
    # 역사적 평균(불리시 37.5% 등) 텍스트가 있으면 참고로 추출
    avg = None
    m = re.search(r"historical average of ([0-9.]+)%", html)
    if m:
        avg = float(m.group(1))
    latest["bull_hist_avg"] = avg
    latest["prev"] = prev
    return latest


def collect():
    return {"cnn_fng": get_cnn_fng(), "aaii": get_aaii()}


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print(json.dumps(collect(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
