"""포트폴리오 보유종목 → 감시대상 자동 동기화.

portfolio-data.js(암호화본)를 .password로 복호화해 현재 보유의 KR 상장종목을 뽑아
watchlist_auto.json 을 재생성한다. 하이브리드 정책:
  - 주식(DART 배당): 고정 기본목록(watchlist.BASE_STOCKS) + 보유 KR 개별주식 자동추가(편출 안 함)
  - ETF(KIND 분배): 보유 KR ETF를 자동추종(편입·편출 자동)
변경 감지 시 알림 메일 발송. 실패해도 감시는 직전 json/폴백으로 계속.

주의: 보유명("Plus K-방산 ETF")과 KIND 정식명("PLUS K방산")이 달라 코드→KIND정식명은
큐레이트 맵(ETF_KIND_NAMES)으로 확정한다. 맵에 없는 새 ETF는 warnings로 플래그.
"""

import base64
import json
import os
import re
from datetime import datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

import watch_config

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)                      # dividends/
_ENC = os.path.join(_ROOT, "portfolio-data.js")
_PW = os.path.join(_ROOT, ".password")
AUTO_PATH = os.path.join(_HERE, "watchlist_auto.json")


def ETF_KIND_NAMES() -> dict:
    """코드 → KIND 정식명 큐레이트 맵(암호화 config). 새 ETF는 config에 추가."""
    return watch_config.etf_kind_names()

# ETF 브랜드(새 ETF 자동 분류용). 6자리 KR 보유 중 이 브랜드/키워드면 ETF로 본다.
_ETF_BRANDS = ("kodex", "tiger", "kbstar", "arirang", "hanaro", "koact", "plus",
               "ace", "rise", "sol", "timefolio", "1q", "kiwoom", "woori", "kosef", "trex")


def _clean(s: str) -> str:
    return s.lstrip("﻿").strip().lstrip("﻿")


def _decrypt_holdings() -> dict:
    """portfolio-data.js 를 복호화해 data dict 반환(PORTFOLIO_PASSWORD env 또는 .password)."""
    pw = os.environ.get("PORTFOLIO_PASSWORD")
    pw = _clean(pw) if pw else _clean(open(_PW, encoding="utf-8-sig").read())
    enc = open(_ENC, encoding="utf-8").read()
    m = re.search(r'PORTFOLIO_ENCRYPTED\s*=\s*"([^"]+)"', enc)
    if not m:
        raise RuntimeError("PORTFOLIO_ENCRYPTED 블록 없음")
    blob = base64.b64decode(m.group(1))
    salt, nonce, ct = blob[:16], blob[16:28], blob[28:]
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000).derive(pw.encode())
    return json.loads(AESGCM(key).decrypt(nonce, ct, None).decode("utf-8"))


def _kr_code(ticker: str) -> str | None:
    m = re.match(r"(\d{6})(?:\.(?:KS|KQ)| (?:KS|KQ))$", ticker or "")
    return m.group(1) if m else None


def _is_etf(name: str) -> bool:
    n = name.lower()
    return ("etf" in n) or ("액티브" in name) or ("iselect" in n) or any(b in n for b in _ETF_BRANDS)


def derive(data: dict) -> dict:
    """보유데이터 → {stocks:{code:name}, etf:{code:kind_name}, warnings:[...]}."""
    stocks: dict[str, str] = {}
    etf: dict[str, str] = {}
    warnings: list[str] = []
    kind_names = ETF_KIND_NAMES()
    for h in data.get("holdings", []):
        code = _kr_code(h.get("ticker", ""))
        if not code:
            continue
        name = h.get("name", "").strip()
        if _is_etf(name):
            if code in kind_names:
                etf[code] = kind_names[code]
            else:
                # 새 ETF: KIND 정식명 미확인 → 보유명으로 잠정 등록 + 플래그
                etf[code] = name
                warnings.append(f"새 ETF {code} '{name}' — KIND 정식명 확인 후 ETF_KIND_NAMES에 추가 필요")
        else:
            stocks[code] = name   # 보유 KR 개별주식(자동추가 대상)
    return {"stocks": stocks, "etf": etf, "warnings": warnings,
            "source_updated": data.get("last_updated", "")}


def load_auto() -> dict | None:
    if os.path.exists(AUTO_PATH):
        try:
            with open(AUTO_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def sync() -> dict:
    """복호화→파생→저장. 반환: {'ok':bool, 'changed':bool, 'diff':..., 'derived':..., 'error':str?}."""
    prev = load_auto()
    try:
        data = _decrypt_holdings()
    except Exception as e:
        return {"ok": False, "changed": False, "error": f"복호화 실패: {e}", "derived": prev}

    derived = derive(data)
    prev_etf = set((prev or {}).get("etf", {}))
    prev_stk = set((prev or {}).get("stocks", {}))
    now_etf, now_stk = set(derived["etf"]), set(derived["stocks"])
    diff = {
        "etf_added": sorted(now_etf - prev_etf), "etf_removed": sorted(prev_etf - now_etf),
        "stock_added": sorted(now_stk - prev_stk), "stock_removed": sorted(prev_stk - now_stk),
    }
    changed = any(diff.values()) or prev is None

    derived["generated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(AUTO_PATH, "w", encoding="utf-8") as f:
        json.dump(derived, f, ensure_ascii=False, indent=2)

    return {"ok": True, "changed": changed, "diff": diff, "derived": derived}
