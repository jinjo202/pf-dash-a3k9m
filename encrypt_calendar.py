"""
encrypt_calendar.py — 보유 분배금 데이터 암호화/복호화

포트폴리오와 동일한 크립토(PBKDF2-SHA256 200k + AES-256-GCM, 공유 .password)를
그대로 재사용한다(encrypt_data.py의 헬퍼 import). 캘린더 탭이 브라우저에서
동일 decryptBlob으로 푼다.

    python encrypt_calendar.py encrypt   # calendar-holdings.plain.js → calendar-holdings.js
    python encrypt_calendar.py decrypt   # 역방향

파일:
    calendar-holdings.plain.js  ← 평문 (gitignored, fetch_calendar_dividends.py 생성)
    calendar-holdings.js        ← 암호화본 (commit)
"""
import base64
import json
import os
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 포트폴리오 암호화와 완전히 동일한 KDF·정화·비번로딩 로직을 재사용.
# (encrypt_data 를 import 하면 그쪽 모듈이 stdout 을 UTF-8 로 래핑한다 — 중복 래핑 금지.)
from encrypt_data import derive_key, _sanitize_nan, get_password, ITERATIONS

HERE = Path(__file__).parent
PLAIN = HERE / "calendar-holdings.plain.js"
ENC = HERE / "calendar-holdings.js"
VAR = "CALENDAR_HOLDINGS"


def encrypt(password: str) -> None:
    if not PLAIN.exists():
        sys.exit(f"평문 없음: {PLAIN.name} (fetch_calendar_dividends.py 먼저)")
    text = PLAIN.read_text(encoding="utf-8")
    m = re.search(rf"window\.{VAR}\s*=\s*(\{{.*?\n\}});", text, re.DOTALL)
    if not m:
        sys.exit(f"{VAR} 블록 못 찾음")
    data = _sanitize_nan(json.loads(m.group(1)))
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")

    salt, nonce = os.urandom(16), os.urandom(12)
    ct = AESGCM(derive_key(password, salt)).encrypt(nonce, payload, None)
    blob = base64.b64encode(salt + nonce + ct).decode("ascii")
    out = (
        f"// 보유 분배금 암호화본 (PBKDF2-SHA256 {ITERATIONS}회 + AES-256-GCM). 평문은 gitignored.\n"
        f"window.{VAR}_ENCRYPTED = {json.dumps(blob)};\n"
        f"window.CAL_PBKDF2_ITERATIONS = {ITERATIONS};\n"
    )
    ENC.write_text(out, encoding="utf-8")
    print(f"암호화 완료: {ENC.name} ({len(payload):,} -> {len(blob):,} B base64)")


def decrypt(password: str) -> None:
    if not ENC.exists():
        sys.exit(f"암호화본 없음: {ENC.name}")
    m = re.search(rf'window\.{VAR}_ENCRYPTED\s*=\s*"([^"]+)"', ENC.read_text(encoding="utf-8"))
    if not m:
        sys.exit("암호화 블록 못 찾음")
    blob = base64.b64decode(m.group(1))
    salt, nonce, ct = blob[:16], blob[16:28], blob[28:]
    plain = AESGCM(derive_key(password, salt)).decrypt(nonce, ct, None)
    data = json.loads(plain.decode("utf-8"))
    out = (
        "// 보유 분배금 평문 (gitignored) — encrypt_calendar.py encrypt 로 calendar-holdings.js 갱신\n"
        f"window.{VAR} = {json.dumps(data, ensure_ascii=False, indent=2)};\n"
    )
    PLAIN.write_text(out, encoding="utf-8")
    print(f"복호화 완료: {PLAIN.name}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("encrypt", "decrypt"):
        sys.exit("사용: python encrypt_calendar.py [encrypt|decrypt] [password]")
    pw = get_password(sys.argv[2] if len(sys.argv) > 2 else None)
    (encrypt if sys.argv[1] == "encrypt" else decrypt)(pw)


if __name__ == "__main__":
    main()
