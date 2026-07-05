"""감시 대상 주식 — 고정 기본목록(암호화 config) + 포트폴리오 자동추가(하이브리드).

BASE_STOCKS/KEYWORD_OVERRIDES 는 public repo 노출 방지 위해 하드코딩하지 않고
watch_config(암호화 dividend-watch.js)에서 읽는다.
watchlist_auto.json 의 'stocks'(보유 KR 개별주식)를 자동 UNION(편출 안 함).
"""

import json
import os

import watch_config

_HERE = os.path.dirname(os.path.abspath(__file__))
_AUTO = os.path.join(_HERE, "watchlist_auto.json")

DEFAULT_DIVIDEND_KEYWORDS: list[str] = [
    "현금ㆍ현물배당결정", "현금·현물배당결정",
    "현금ㆍ현물배당 결정", "현금·현물배당 결정",
]


def base_stocks() -> dict[str, str]:
    return watch_config.stocks()


def _overrides() -> dict[str, list]:
    return watch_config.keyword_overrides()


def _auto_stocks() -> dict[str, str]:
    if os.path.exists(_AUTO):
        try:
            with open(_AUTO, encoding="utf-8") as f:
                return dict(json.load(f).get("stocks", {}))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _merged() -> dict[str, str]:
    m = dict(base_stocks())    # 고정(config) 우선
    m.update(_auto_stocks())   # 보유 개별주식 자동추가
    return m


def get_stock_codes() -> list[str]:
    return list(_merged().keys())


def get_stock_name(stock_code: str) -> str:
    return _merged().get(stock_code, "알 수 없음")


def get_keywords(stock_code: str) -> list[str]:
    return _overrides().get(stock_code, DEFAULT_DIVIDEND_KEYWORDS)
