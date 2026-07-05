"""상태 파일 암호화 커밋백 — 러너(GitHub Actions)에서 상태 지속용.

state.json(중복방지) + reminders.json(기준일 리마인드) + watchlist_auto.json(변경감지 기준)
을 하나로 묶어 ../dividend-state.js(암호화, commit)로 저장/복원.

    python state_crypto.py decrypt   # dividend-state.js → state.json/reminders.json/watchlist_auto.json
    python state_crypto.py encrypt   # 위 3개 → dividend-state.js

PORTFOLIO_PASSWORD(env) 또는 ../.password 사용.
"""

import base64
import json
import os
import re
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_ENC = os.path.join(_ROOT, "dividend-state.js")
_PW_FILE = os.path.join(_ROOT, ".password")

_FILES = {
    "state": os.path.join(_HERE, "state.json"),
    "reminders": os.path.join(_HERE, "reminders.json"),
    "watchlist_auto": os.path.join(_HERE, "watchlist_auto.json"),
}


def _clean(s: str) -> str:
    return s.lstrip("﻿").strip().lstrip("﻿")


def _password() -> str:
    pw = os.environ.get("PORTFOLIO_PASSWORD")
    if pw:
        return _clean(pw)
    if os.path.exists(_PW_FILE):
        return _clean(open(_PW_FILE, encoding="utf-8-sig").read())
    sys.exit("PORTFOLIO_PASSWORD 없음")


def _key(pw, salt):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000).derive(pw.encode())


def encrypt():
    bundle = {}
    for name, path in _FILES.items():
        if os.path.exists(path):
            try:
                bundle[name] = json.load(open(path, encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                bundle[name] = None
    payload = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    salt, nonce = os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(_password(), salt)).encrypt(nonce, payload, None)
    blob = base64.b64encode(salt + nonce + ct).decode()
    open(_ENC, "w", encoding="utf-8").write(
        "// 배당 모니터 상태 암호화본 (state+reminders+watchlist_auto). 러너 커밋백용.\n"
        f'window.DIVIDEND_STATE_ENCRYPTED = "{blob}";\n')
    print(f"상태 암호화: dividend-state.js ({len(blob)} bytes)")


def decrypt():
    if not os.path.exists(_ENC):
        print("dividend-state.js 없음 — 최초 실행(빈 상태로 시작)")
        return
    m = re.search(r'ENCRYPTED\s*=\s*"([^"]+)"', open(_ENC, encoding="utf-8").read())
    blob = base64.b64decode(m.group(1))
    salt, nonce, ct = blob[:16], blob[16:28], blob[28:]
    bundle = json.loads(AESGCM(_key(_password(), salt)).decrypt(nonce, ct, None).decode("utf-8"))
    for name, path in _FILES.items():
        if bundle.get(name) is not None:
            json.dump(bundle[name], open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("상태 복원: state.json / reminders.json / watchlist_auto.json")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("encrypt", "decrypt"):
        sys.exit("사용: python state_crypto.py [encrypt|decrypt]")
    (encrypt if sys.argv[1] == "encrypt" else decrypt)()
