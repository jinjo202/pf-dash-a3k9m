"""감시 ETF + 공시 종목명 정확 매칭 — 보유 자동추종(watchlist_auto.json).

ETF 목록은 watchlist_auto.json 의 'etf'(보유 KR ETF, 코드→KIND정식명)를 사용,
없으면 FALLBACK(직전 6종)으로 폴백.

매칭: 정규화(공백·하이픈·점·괄호 제거, 소문자, 끝 'etf' 제거) 후 **정확 일치**.
→ 변형상품(레버리지/중소형/TR 등) 오탐 방지 + 보유명↔KIND명 표기차 흡수.
"""

import json
import os
import re

import watch_config

_HERE = os.path.dirname(os.path.abspath(__file__))
_AUTO = os.path.join(_HERE, "watchlist_auto.json")


def current_etfs() -> dict[str, str]:
    """감시 ETF (코드→KIND정식명). 보유 자동추종 json 우선, 없으면 config 폴백."""
    if os.path.exists(_AUTO):
        try:
            with open(_AUTO, encoding="utf-8") as f:
                etf = dict(json.load(f).get("etf", {}))
            if etf:
                return etf
        except (json.JSONDecodeError, OSError):
            pass
    return watch_config.etf_kind_names()   # 폴백: config의 큐레이트 맵(노출 방지)


def _clean(s: str) -> str:
    s = re.sub(r"[\s\-.()]", "", s).lower()
    return s[:-3] if s.endswith("etf") else s


def find_matched_etf(disclosure_stock_name: str) -> str | None:
    """공시 종목명이 감시 ETF와 정규화 후 '정확히' 일치하면 코드 반환, 아니면 None."""
    name = _clean(disclosure_stock_name)
    for code, canonical in current_etfs().items():
        if name == _clean(canonical):
            return code
    return None


def get_etf_name(code: str) -> str:
    return current_etfs().get(code, "알 수 없음")
