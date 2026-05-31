"""
한국 투자자별 수급(외국인/기관/개인) 자동 수집 → kr_flows.json (평문, 공개 데이터).

소스: 네이버 금융 투자자별 매매동향(일별, KOSPI). 단위 억원 → 조원 변환.
- YTD 일별 수집(연초~현재) → 누적 시계열 + 최근월 일별 + 월/최근일 요약.
fetch_macro.py가 이 파일을 읽어 macro-data.js의 한국 수급 지표·시계열을 갱신.

방어적 설계: 유효 데이터를 못 받으면 기존 kr_flows.json 보존.
투자자예탁금은 무료 안정 소스가 없어 fetch_macro.py의 수동 시드(KR_DEPOSIT_SERIES) 유지.
"""
import json
import re
import sys
import io
import urllib.request
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "kr_flows.json"
URL = "https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={d}&sosok=01&page={p}"
MAX_PAGES = 14


def fetch_page(bizdate, page):
    req = urllib.request.Request(
        URL.format(d=bizdate, p=page),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                 "Referer": "https://finance.naver.com/sise/"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("euc-kr", errors="replace")


def parse_rows(html):
    """일별 행 → {date 'YY.MM.DD': [개인, 외국인, 기관계]} (억원, int)."""
    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub("<[^>]+>", "", c).strip().replace("\xa0", "")
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        cells = [c for c in cells if c != ""]
        if len(cells) >= 4 and re.match(r"\d{2}\.\d{2}\.\d{2}", cells[0]):
            try:
                out[cells[0]] = [int(cells[1].replace(",", "")),
                                 int(cells[2].replace(",", "")),
                                 int(cells[3].replace(",", ""))]
            except ValueError:
                continue
    return out


def iso(d):  # 'YY.MM.DD' → '20YY-MM-DD'
    return "20" + d.replace(".", "-")


def main():
    today = date.today()
    bizdate = today.strftime("%Y%m%d")
    yy = today.strftime("%y")  # '26'
    rows = {}
    try:
        for p in range(1, MAX_PAGES + 1):
            page = parse_rows(fetch_page(bizdate, p))
            if not page:
                break
            rows.update(page)
            earliest = min(page)  # 'YY.MM.DD'
            if earliest < f"{yy}.01.01":  # 연초 지나면 중단
                break
    except Exception as e:
        print(f"[err] 네이버 수집 실패: {type(e).__name__} {e}")

    if not rows:
        print("유효 데이터 없음 — 기존 kr_flows.json 보존")
        return

    dates = sorted(rows)  # 'YY.MM.DD' 정렬 = 시간순
    ytd = [d for d in dates if d.startswith(yy)]  # 올해
    latest = dates[-1]
    ym = latest[:5]  # 'YY.MM'
    month_days = [d for d in ytd if d.startswith(ym)]

    def tj(x):  # 억원 → 조원
        return round(x / 10000.0, 2)

    # YTD 누적 시계열 (조원)
    cum = {"retail": 0, "foreign": 0, "inst": 0}
    ytd_cum = {"dates": [], "retail": [], "foreign": [], "inst": []}
    for d in ytd:
        r = rows[d]
        cum["retail"] += r[0]; cum["foreign"] += r[1]; cum["inst"] += r[2]
        ytd_cum["dates"].append(iso(d))
        ytd_cum["retail"].append(tj(cum["retail"]))
        ytd_cum["foreign"].append(tj(cum["foreign"]))
        ytd_cum["inst"].append(tj(cum["inst"]))

    # 최근월 일별 (조원)
    month_daily = {"dates": [], "retail": [], "foreign": [], "inst": []}
    for d in month_days:
        r = rows[d]
        month_daily["dates"].append(iso(d))
        month_daily["retail"].append(tj(r[0]))
        month_daily["foreign"].append(tj(r[1]))
        month_daily["inst"].append(tj(r[2]))

    def msum(idx):
        return round(sum(rows[d][idx] for d in month_days) / 10000.0, 1)

    lc = rows[latest]
    out = {
        "as_of": today.isoformat(),
        "source": "naver-finance",
        "month": "20" + ym,
        "unit": "조원",
        "mtd": {"retail": msum(0), "foreign": msum(1), "inst": msum(2), "days": len(month_days)},
        "ytd_total": {"retail": ytd_cum["retail"][-1] if ytd_cum["retail"] else None,
                      "foreign": ytd_cum["foreign"][-1] if ytd_cum["foreign"] else None,
                      "inst": ytd_cum["inst"][-1] if ytd_cum["inst"] else None},
        "latest": {"date": latest, "retail": tj(lc[0]), "foreign": tj(lc[1]), "inst": tj(lc[2])},
        "ytd_cum": ytd_cum,
        "month_daily": month_daily,
        "deposit": None,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    yt = out["ytd_total"]
    print(f"저장: {OUT.name}  YTD누적(조원) 외국인 {yt['foreign']}·기관 {yt['inst']}·개인 {yt['retail']} "
          f"({len(ytd)}일), 최근월 {ym} {len(month_days)}일, 최근 {latest}")


if __name__ == "__main__":
    main()
