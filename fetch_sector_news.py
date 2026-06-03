"""종목/섹터별 최신 뉴스 자동 수집 (Google News RSS, 무료·키 불필요).

각 holding에 매핑된 섹터 키워드로 구글 뉴스를 검색해 최근 헤드라인+링크+날짜를
holding-news.js (평문)로 저장. 대시보드의 알파 분해 상세에서 "📰 최근 뉴스(자동)"로
표시. 매일 cron이 실행 → 항상 최신.

- 정성 분석 코멘트(HOLDING_NOTES)는 portfolio.html에 수동 큐레이션으로 유지.
- 이 스크립트는 '최신 뉴스 링크'만 자동 갱신 (정성 해석은 안 함).
"""
import sys, io, re, html, json, time, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "holding-news.js"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# holding 이름 → 구글뉴스 검색 키워드
# (포트폴리오 holding name과 정확히 일치해야 매칭됨)
SECTOR_KEYWORDS = {
    "KODEX 200 ETF":                         "코스피 증시 전망",
    "KODEX 코스닥150 ETF":                    "코스닥 지수 부진",
    "KODEX AI전력핵심설비 ETF":               "전력기기 전력설비 주가",
    "KoAct 바이오헬스케어액티브":             "제약 바이오 주가 코스닥",
    "Hanaro 원자력 iSelect":                  "원자력 원전주 주가",
    "Plus K-방산 ETF":                        "방산주 K방산 주가",
    "KoAct 글로벌AI&로봇액티브 ETF":          "AI 반도체 로봇 주가",
    "삼성 ESG 착한 책임투자":                 "ESG 책임투자 펀드",
    "마이다스 책임투자":                      "마이다스 책임투자 펀드",
    "KODEX 자동차":                           "자동차주 현대차 기아 주가",
    # 미국·글로벌
    "State Street Tech ETF (XLK)":            "미국 기술주 나스닥 빅테크",
    "SPDR Communication ETF (XLC)":           "미국 커뮤니케이션 구글 메타 주가",
    "SS Industrial Select SPDR ETF (XLI)":    "미국 산업재 제조업 주가",
    "SS Materials Select SPDR ETF (XLB)":     "미국 소재 원자재 주가",
    "T.Rowe Capital Appreciation ETF (TCAF)": "미국 증시 S&P500 전망",
    "Invesco NASDAQ-100 ETF (QQQM)":          "나스닥100 빅테크 주가",
    "KODEX S&P500(H)":                        "S&P500 미국증시 전망",
    "iShares MSCI Emerging (EEM)":            "신흥국 이머징 증시",
    "Dimensional International Value (DFIV)":  "글로벌 가치주 증시",
    "Xtrackers DAX ETF (XDAX)":               "독일 DAX 유럽증시",
    "Fidelity European Dividend":             "유럽 배당주 증시",
}

N_PER = 4  # 종목당 최대 뉴스 수


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
        # "제목 - 언론사" 형태에서 언론사 분리
        src = html.unescape(sm.group(1)).strip() if sm else ""
        if not src and " - " in title:
            title, src = title.rsplit(" - ", 1)
        # 날짜 → YYYY-MM-DD
        date = ""
        if pm:
            try:
                date = datetime.strptime(pm.group(1).strip()[:25], "%a, %d %b %Y %H:%M:%S").date().isoformat()
            except Exception:
                date = pm.group(1).strip()[:16]
        out.append({"title": title[:90], "url": lm.group(1).strip(),
                    "source": src[:20], "date": date})
    return out


def main():
    print(f"=== 종목별 뉴스 수집 (Google News RSS, {datetime.now().date()}) ===")
    news = {}
    for name, kw in SECTOR_KEYWORDS.items():
        items = fetch_news(kw)
        if items:
            news[name] = items
            print(f"  [ok] {name[:34]:34s} ← \"{kw}\"  ({len(items)}건)")
        else:
            print(f"  [--] {name[:34]:34s} ← \"{kw}\"  (없음)")
        time.sleep(0.4)  # rate-limit 매너

    OUT.write_text(
        "// 종목/섹터별 최신 뉴스 (Google News RSS, 평문 공개데이터). fetch_sector_news.py로 자동 갱신.\n"
        f"// 갱신: {datetime.now().isoformat(timespec='seconds')}\n"
        f"window.HOLDING_NEWS = {json.dumps(news, ensure_ascii=False, indent=1)};\n",
        encoding="utf-8",
    )
    print(f"\n저장: {OUT.name}  ({len(news)}개 종목)")


if __name__ == "__main__":
    main()
