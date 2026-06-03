# -*- coding: utf-8 -*-
"""
fetch_constituent_news.py — ETF 내 상위 5종목 각각의 최신 뉴스 자동 수집.

portfolio-data.plain.js 의 각 holding 의 top_holdings 필드(yfinance + 운용사 큐레이션)에서
구성종목 이름을 모아 deduplicate 후, Google News RSS 로 종목당 최근 뉴스 4건을 수집.
출력: constituent-news.js (window.CONSTITUENT_NEWS = { 종목명: [{title,url,source,date},...] }).

portfolio.html 의 알파 분해 detail 행에서 각 ETF 의 alpha-h-card 안 종목별 뉴스로 표시.
fetch_sector_news.py 와 같은 패턴 — 무료 RSS, 키 불필요. cron 매일 갱신.
"""
import sys, io, re, html, json, time, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
PLAIN = HERE / "portfolio-data.plain.js"
OUT = HERE / "constituent-news.js"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

N_PER = 4  # 종목당 최대 뉴스 수
SLEEP = 0.4  # Google News rate-limit 매너


def extract_portfolio_obj(text):
    """portfolio-data.plain.js 에서 window.PORTFOLIO_DATA = {...} 의 {...} 부분만 추출."""
    start = text.index("{", text.index("PORTFOLIO_DATA"))
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError("PORTFOLIO_DATA 객체 닫는 } 못 찾음")


def collect_constituents(plain_path):
    """모든 holding 의 top_holdings 에서 구성종목 이름 추출 (중복 제거, 순서 유지)."""
    text = plain_path.read_text(encoding="utf-8")
    data = json.loads(extract_portfolio_obj(text))
    seen = set()
    names = []
    for h in (data.get("holdings") or []):
        for th in (h.get("top_holdings") or []):
            nm = (th.get("name") or "").strip()
            if nm and nm not in seen:
                seen.add(nm)
                names.append(nm)
    return names


def fetch_news(keyword):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": keyword, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    try:
        req = urllib.request.Request(url, headers=UA)
        xml = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  [err] {keyword}: {e}")
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
                date = datetime.strptime(
                    pm.group(1).strip()[:25], "%a, %d %b %Y %H:%M:%S"
                ).date().isoformat()
            except Exception:
                date = pm.group(1).strip()[:16]
        out.append({"title": title[:100], "url": lm.group(1).strip(),
                    "source": src[:24], "date": date})
    return out


def main():
    if not PLAIN.exists():
        sys.exit(f"필요: {PLAIN} (평문 portfolio-data). "
                 "encrypt_data.py decrypt 로 복호화 후 실행.")
    names = collect_constituents(PLAIN)
    print(f"=== ETF 상위 구성종목 뉴스 수집 (Google News RSS, {datetime.now().date()}) ===")
    print(f"unique constituents: {len(names)}")
    news = {}
    for nm in names:
        items = fetch_news(nm + " 주가")  # "{종목명} 주가" 검색 — 주가 영향 헤드라인 편향
        if items:
            news[nm] = items
            print(f"  [ok] {nm[:30]:30s} ({len(items)}건)")
        else:
            print(f"  [--] {nm[:30]:30s} (없음)")
        time.sleep(SLEEP)

    OUT.write_text(
        "// ETF 상위 구성종목별 최신 뉴스 (Google News RSS). fetch_constituent_news.py 로 자동 갱신.\n"
        f"// 갱신: {datetime.now().isoformat(timespec='seconds')}\n"
        f"// 총 {len(news)}개 종목.\n"
        f"window.CONSTITUENT_NEWS = {json.dumps(news, ensure_ascii=False, indent=1)};\n",
        encoding="utf-8",
    )
    print(f"\n저장: {OUT.name}  ({len(news)}개 종목)")


if __name__ == "__main__":
    main()
