"""감시 config 로더 — 보유목록을 코드에 하드코딩하지 않고 암호화 config에서 읽는다.

public repo 노출 방지: stocks / keyword_overrides / etf_kind_names 는 전부
../dividend-watch.js(암호화, PORTFOLIO_PASSWORD) 또는 ../dividend-watch.plain.js(gitignored)에만 존재.
로컬·클라우드(GitHub Actions) 공통.
"""

import base64
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_PLAIN = os.path.join(_ROOT, "dividend-watch.plain.js")
_ENC = os.path.join(_ROOT, "dividend-watch.js")
_PW_FILE = os.path.join(_ROOT, ".password")

_cache: dict | None = None


def _clean(s: str) -> str:
    return s.lstrip("﻿").strip().lstrip("﻿")


def _password() -> str | None:
    pw = os.environ.get("PORTFOLIO_PASSWORD")
    if pw:
        return _clean(pw)
    if os.path.exists(_PW_FILE):
        return _clean(open(_PW_FILE, encoding="utf-8-sig").read())
    return None


def load() -> dict:
    """config dict 반환(캐시). 실패 시 {} (호출부는 폴백)."""
    global _cache
    if _cache is not None:
        return _cache
    text = None
    if os.path.exists(_PLAIN):
        text = open(_PLAIN, encoding="utf-8").read()
    elif os.path.exists(_ENC):
        pw = _password()
        if pw:
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                from cryptography.hazmat.primitives import hashes
                blob = base64.b64decode(re.search(r'ENCRYPTED\s*=\s*"([^"]+)"', open(_ENC, encoding="utf-8").read()).group(1))
                salt, nonce, ct = blob[:16], blob[16:28], blob[28:]
                key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000).derive(pw.encode())
                text = AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
            except Exception as e:
                print(f"⚠️ config 복호화 실패: {e}")
    if not text:
        _cache = {}
        return _cache
    m = re.search(r"window\.DIVIDEND_WATCH\s*=\s*(\{.*?\n\});", text, re.DOTALL)
    if not m:
        _cache = {}
        return _cache
    obj = re.sub(r"//[^\n]*", "", m.group(1))     # JS 주석 제거
    obj = re.sub(r",(\s*[}\]])", r"\1", obj)         # 트레일링 콤마 제거
    _cache = json.loads(obj)
    return _cache


def stocks() -> dict[str, str]:
    return dict(load().get("stocks", {}))


def keyword_overrides() -> dict[str, list]:
    return dict(load().get("keyword_overrides", {}))


def etf_kind_names() -> dict[str, str]:
    return dict(load().get("etf_kind_names", {}))
