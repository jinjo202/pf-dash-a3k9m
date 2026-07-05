"""KIND ETF 분배 공시 조회 (requests + BeautifulSoup, Selenium 불필요).

배당결정은 DART(거래소공시 I)로 잡지만, ETF 이익분배는 KIND의 ETF 공시 페이지에만 뜬다.
disclosurebystocktype.do (searchDisclosureByStockTypeEtfSub) 로 '분배' 관련 공시를 가져온다.
"""

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

_URL = "https://kind.krx.co.kr/disclosure/disclosurebystocktype.do"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://kind.krx.co.kr/disclosure/disclosurebystocktype.do?method=searchDisclosureByStockTypeEtf",
    "Content-Type": "application/x-www-form-urlencoded",
}

# 분배 관련으로 볼 키워드 (이익분배/이익금분배/분배금/분배락 등 모두 '분배' 포함)
DIST_KEYWORD = "분배"


@dataclass
class EtfDisclosure:
    date_str: str      # "2026-06-26 18:22"
    stock_name: str    # 공시상의 ETF 종목명
    report_nm: str     # 공시 제목
    acptno: str        # KIND 접수번호(고유 id)

    @property
    def kind_url(self) -> str:
        return f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={self.acptno}"


def fetch_distributions(
    from_date: str, to_date: str, etf_name: str = "", max_pages: int = 6
) -> list[EtfDisclosure]:
    """기간 내 ETF '분배' 관련 공시를 반환. from/to: 'YYYY-MM-DD'.

    etf_name 지정 시 해당 종목명(prefix)으로 서버측 필터 → 분배 성수기 대량공시에도
    600행 상한에 안 걸림(감시 6종목은 이름별로 조회 권장).
    """
    out: list[EtfDisclosure] = []
    for page in range(1, max_pages + 1):
        payload = {
            "method": "searchDisclosureByStockTypeEtfSub",
            "forward": "disclosurebystocktype_etf_sub",
            "currentPageSize": "100", "pageIndex": str(page),
            "orderMode": "1", "orderStat": "D",
            "etfIsuSrtCd": "", "reportCd": "", "reportTmp": "",
            "etfIsuSrtNm": etf_name, "reportNm": DIST_KEYWORD,   # 종목명 + '분배' 서버필터
            "fromDate": from_date, "toDate": to_date,
        }
        resp = requests.post(_URL, data=payload, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        rows = _parse_rows(resp.text)
        out.extend(rows)
        if len(rows) < 100:
            break
    return out


def _parse_rows(html: str) -> list[EtfDisclosure]:
    soup = BeautifulSoup(html, "html.parser")
    result: list[EtfDisclosure] = []
    for tr in soup.select("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        a = tds[3].find("a", onclick=re.compile("openDisclsViewer"))
        if not a:
            continue
        m = re.search(r"openDisclsViewer\('(\d+)'", a.get("onclick", ""))
        if not m:
            continue
        title = (a.get("title") or a.get_text()).strip()
        if DIST_KEYWORD not in title:   # 안전망: 제목에 '분배' 없으면 스킵
            continue
        result.append(EtfDisclosure(
            date_str=tds[1].get_text(strip=True),
            stock_name=tds[2].get_text(strip=True),
            report_nm=title,
            acptno=m.group(1),
        ))
    return result
