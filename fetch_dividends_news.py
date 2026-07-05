"""배당주 유니버스 종목별 최신 뉴스 수집 (Google News RSS, 무료·키 불필요).

dividends-data.js 의 각 종목을 이름으로 구글뉴스 검색 → 최근 헤드라인+링크+날짜+언론사를
dividends-news.js (window.DIVIDENDS_NEWS) 로 저장. dividends.html 상세 패널의
"📰 관련 뉴스"에서 링크로 표시. 매일 cron 갱신.

- KR 종목: 한국어 검색(hl=ko), US/EU 종목: 영어 검색(hl=en)
- 종목 키는 yf 심볼(고유). 지역은 yf 접미사로 판별.
"""
import sys, io, re, html, json, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = Path(__file__).parent
SRC = HERE / "dividends-data.js"
OUT = HERE / "dividends-news.js"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
N_PER = 5  # 종목당 최대 뉴스 수

EU_SUFFIX = re.compile(r"\.(L|PA|DE|MI|SW|MC|AS|BR|VI|ST|HE|OL|LS|SG|F)$")


def parse_universe(js: str):
    """dividends-data.js → [{yf, t, n, nEn, region}]"""
    out = []
    pat = re.compile(
        r't:"([^"]+)",\s*yf:"([^"]+)",\s*(?:held:true,\s*)?n:"([^"]+)",\s*nEn:"([^"]+)"'
    )
    for m in pat.finditer(js):
        t, yf, n, nEn = m.group(1), m.group(2), m.group(3), m.group(4)
        if yf.endswith(".KS") or yf.endswith(".KQ"):
            region = "KR"
        elif EU_SUFFIX.search(yf):
            region = "EU"
        else:
            region = "US"
        out.append({"yf": yf, "t": t, "n": n, "nEn": nEn, "region": region})
    return out


def fetch_news(query, ko=True):
    if ko:
        params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=UA)
        xml = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  [err] {query}: {e}")
        return []
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)[:N_PER]:
        tm = re.search(r"<title>(.*?)</title>", it, re.DOTALL)
        lm = re.search(r"<link>(.*?)</link>", it, re.DOTALL)
        pm = re.search(r"<pubDate>(.*?)</pubDate>", it, re.DOTALL)
        sm = re.search(r"<source[^>]*>(.*?)</source>", it, re.DOTALL)
        if not tm or not lm:
            continue
        title = html.unescape(re.sub(r"<.*?>", "", tm.group(1))).strip()
        src = html.unescape(sm.group(1)).strip() if sm else ""
        if not src and " - " in title:
            title, src = title.rsplit(" - ", 1)
        date = ""
        if pm:
            try:
                date = datetime.strptime(pm.group(1).strip()[:25], "%a, %d %b %Y %H:%M:%S").date().isoformat()
            except Exception:
                date = pm.group(1).strip()[:16]
        out.append({"t": title[:100], "u": lm.group(1).strip(),
                    "s": src[:24], "d": date})
    return out


def _kst_today():
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")


def already_today():
    if not OUT.exists():
        return False
    try:
        m = re.search(r'"as_of":\s*"(\d{4}-\d{2}-\d{2})', OUT.read_text(encoding="utf-8"))
        return bool(m) and m.group(1) == _kst_today()
    except Exception:
        return False


def main():
    if "--force" not in sys.argv and already_today():
        print("skip: dividends-news 이미 오늘자 — 재수집 생략 (--force 로 강제)")
        return
    js = SRC.read_text(encoding="utf-8")
    uni = parse_universe(js)
    print(f"=== 배당주 종목별 뉴스 수집 (Google News RSS, {datetime.now().date()}) · {len(uni)}종목 ===")
    news = {}
    for i, s in enumerate(uni, 1):
        if s["region"] == "KR":
            q = s["n"] + " 주가"
            items = fetch_news(q, ko=True)
        else:
            q = s["nEn"] + " stock dividend"
            items = fetch_news(q, ko=False)
        if items:
            news[s["yf"]] = items
        tag = "ok" if items else "--"
        print(f"  [{tag}] {s['t']:8s} {s['n'][:20]:20s} ({len(items)}건)")
        time.sleep(0.4)
    kst = timezone(timedelta(hours=9))
    as_of = datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")
    payload = {"as_of": as_of, "source": "Google News RSS", "data": news}
    OUT.write_text(
        "// 배당주 종목별 최신 뉴스 (Google News RSS, 평문 공개데이터). fetch_dividends_news.py 로 자동 갱신.\n"
        "window.DIVIDENDS_NEWS = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"\n저장: {OUT.name} ({len(news)}/{len(uni)}개 종목) · {as_of}")


if __name__ == "__main__":
    main()
