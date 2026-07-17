"""DART OpenAPI 클라이언트 (lean).

dart-mail-sender/dart_api_client.py 에서 배당공시 모니터링에 필요한 부분만 추림:
  - corpCode.xml 다운로드 → stock_code ↔ corp_code 매핑
  - list.json 공시 목록 조회
PDF/ETF/리마인드 등 부가기능은 의도적으로 제외(실패 표면 최소화).
"""

import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests


@dataclass
class Disclosure:
    corp_code: str
    corp_name: str
    stock_code: str
    corp_cls: str
    report_nm: str
    rcept_no: str
    flr_nm: str
    rcept_dt: str
    rm: str

    @classmethod
    def from_dict(cls, data: dict) -> "Disclosure":
        return cls(
            corp_code=data.get("corp_code", ""),
            corp_name=data.get("corp_name", ""),
            stock_code=data.get("stock_code", ""),
            corp_cls=data.get("corp_cls", ""),
            report_nm=data.get("report_nm", ""),
            rcept_no=data.get("rcept_no", ""),
            flr_nm=data.get("flr_nm", ""),
            rcept_dt=data.get("rcept_dt", ""),
            rm=data.get("rm", ""),
        )

    @property
    def dart_url(self) -> str:
        return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={self.rcept_no}"

    def __str__(self) -> str:
        return f"[{self.rcept_dt}] {self.corp_name} ({self.stock_code}) - {self.report_nm}"


class DartApiClient:
    BASE_URL = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session = requests.Session()
        self._stock_to_corp: dict[str, str] = {}   # stock_code → corp_code

    def initialize(self) -> None:
        """corpCode.xml 다운로드 → 종목코드↔기업고유번호 매핑 구축."""
        url = f"{self.BASE_URL}/corpCode.xml"
        resp = self._session.get(url, params={"crtfc_key": self.api_key}, timeout=30)
        resp.raise_for_status()

        # status가 JSON 에러로 올 수도 있음(키 오류 등) → ZIP 파싱 실패로 잡아 알림
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                xml_name = [n for n in zf.namelist() if n.endswith(".xml")][0]
                xml_bytes = zf.read(xml_name)
        except zipfile.BadZipFile:
            raise RuntimeError(
                f"corpCode.xml 응답이 ZIP이 아님(키 오류 가능). 앞 200자: {resp.text[:200]}"
            )

        root = ET.fromstring(xml_bytes)
        mapped = 0
        for elem in root.iter("list"):
            corp_code = (elem.findtext("corp_code") or "").strip()
            stock_code = (elem.findtext("stock_code") or "").strip()
            if corp_code and stock_code:
                self._stock_to_corp[stock_code] = corp_code
                mapped += 1
        print(f"✅ corp_code 매핑 완료: 상장사 {mapped}개")

    def get_corp_code(self, stock_code: str) -> str | None:
        return self._stock_to_corp.get(stock_code)

    def fetch_disclosures(
        self,
        begin_date: str,
        end_date: str,
        pblntf_ty: str | None = "I",
        page_no: int = 1,
        page_count: int = 100,
        corp_code: str | None = None,
    ) -> list[Disclosure]:
        """공시 목록 조회. pblntf_ty='I'=거래소공시(현금ㆍ현물배당결정 포함).

        corp_code 지정 시 해당 기업만(백필: 3개월 기간제한 없이 장기간 가능).
        주의: 배당결정은 주요사항보고(B)가 아니라 거래소공시(I)다(실증 확인).
        """
        params: dict[str, str | int] = {
            "crtfc_key": self.api_key,
            "bgn_de": begin_date,
            "end_de": end_date,
            "page_no": page_no,
            "page_count": page_count,
        }
        if pblntf_ty:
            params["pblntf_ty"] = pblntf_ty
        if corp_code:
            params["corp_code"] = corp_code

        resp = self._session.get(f"{self.BASE_URL}/list.json", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status")
        if status == "013":   # 조회 결과 없음
            return []
        if status != "000":
            raise RuntimeError(f"DART API 오류 ({status}): {data.get('message', '?')}")
        return [Disclosure.from_dict(item) for item in data.get("list", [])]

    def fetch_all(
        self, begin_date: str, end_date: str, pblntf_ty: str | None = "I"
    ) -> list[Disclosure]:
        import time
        out: list[Disclosure] = []
        page_no = 1
        while True:
            page = self.fetch_disclosures(begin_date, end_date, pblntf_ty, page_no, 100)
            out.extend(page)
            if len(page) < 100:
                break
            page_no += 1
            time.sleep(0.1)
        return out

    def close(self) -> None:
        self._session.close()
