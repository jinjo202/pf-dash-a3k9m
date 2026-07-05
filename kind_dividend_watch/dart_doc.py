"""DART 공시 원문(document.xml) API로 배당/분배 상세 필드 추출.

공식 API라 HTML 스크래핑보다 안정적. 실패는 조용히 {} 반환(알림은 계속 발송).
- 현금ㆍ현물배당결정: 배당구분/1주당 배당금/시가배당률/배당금총액/배당기준일/지급예정일
- 맥쿼리인프라 주주명부폐쇄기간또는기준일설정: 기준일/설정사유
  (분배 '금액'은 KIND 전용 '투자회사의 금전분배 결의'에만 있어 API로 못 가져옴)
"""

import io
import re
import zipfile

import requests

_DOC_URL = "https://opendart.fss.or.kr/api/document.xml"


def _flat_text(api_key: str, rcept_no: str) -> str | None:
    try:
        r = requests.get(_DOC_URL, params={"crtfc_key": api_key, "rcept_no": rcept_no}, timeout=20)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            raw = zf.read(zf.namelist()[0])
    except (requests.RequestException, zipfile.BadZipFile, IndexError, KeyError):
        return None
    txt = raw.decode("utf-8", "replace")
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def fetch_detail(api_key: str, rcept_no: str) -> dict:
    """원문에서 배당/분배 핵심 필드를 뽑아 dict로 반환(없으면 {})."""
    txt = _flat_text(api_key, rcept_no)
    if not txt:
        return {}

    def g(pat: str) -> str | None:
        m = re.search(pat, txt)
        return m.group(1).strip() if m else None

    out: dict[str, str] = {}
    # ── 현금ㆍ현물배당결정 ──
    out["배당구분"] = g(r"배당구분\s*(\S+)")
    out["1주당 배당금"] = g(r"1주당 배당금\(원\)\s*보통주식\s*([\d,]+)")
    out["시가배당률"] = g(r"시가배당률\(%\)\s*보통주식\s*([\d.]+)")
    out["배당금총액"] = g(r"배당금총액\(원\)\s*([\d,]+)")
    out["배당기준일"] = g(r"배당기준일\s*(\d{4}-\d{2}-\d{2})")
    out["지급예정일"] = g(r"배당금지급 예정일자\s*(\d{4}-\d{2}-\d{2})")
    # ── 맥쿼리인프라 기준일설정 (배당결정이 아닐 때) ──
    if not out.get("배당기준일"):
        out["기준일"] = g(r"(?:^|[^배당])기준일\s*(\d{4}-\d{2}-\d{2})")
        out["사유"] = g(r"설정사유\s*(.+?)\s*4\.\s")

    return {k: v for k, v in out.items() if v}
