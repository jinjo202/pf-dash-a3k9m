"""
포트폴리오 데이터 암호화/복호화 (AES-256-GCM + PBKDF2-SHA256)

사용:
    python encrypt_data.py encrypt              # 비밀번호 프롬프트
    python encrypt_data.py encrypt PASSWORD     # 명령행 인자
    python encrypt_data.py decrypt              # 비밀번호 프롬프트
    PORTFOLIO_PASSWORD=xxx python encrypt_data.py encrypt   # 환경변수

파일:
    portfolio-data.plain.js  ← 평문 (gitignored, 로컬 작업용)
    portfolio-data.js        ← 암호화본 (Git에 commit)
"""
import base64
import getpass
import json
import os
import re
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:
    sys.exit("cryptography 필요: pip install cryptography")

HERE = Path(__file__).parent
PLAIN_PATH = HERE / "portfolio-data.plain.js"
ENC_PATH = HERE / "portfolio-data.js"
PW_FILE = HERE / ".password"
ITERATIONS = 200_000


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def get_password(arg: str | None) -> str:
    if arg:
        return arg.strip()
    env = os.environ.get("PORTFOLIO_PASSWORD")
    if env:
        return env.strip()
    if PW_FILE.exists():
        return PW_FILE.read_text(encoding="utf-8").strip()
    pw = getpass.getpass("비밀번호: ")
    if not pw:
        sys.exit("비밀번호가 비어 있습니다.")
    return pw.strip()


def encrypt(password: str) -> None:
    if not PLAIN_PATH.exists():
        sys.exit(f"평문 파일 없음: {PLAIN_PATH.name}\n  → decrypt 먼저 실행하거나 평문 파일을 만들어주세요.")

    text = PLAIN_PATH.read_text(encoding="utf-8")
    m = re.search(r"window\.PORTFOLIO_DATA\s*=\s*(\{.*?\n\});", text, re.DOTALL)
    if not m:
        sys.exit("PORTFOLIO_DATA 블록을 찾지 못함")
    obj_str = m.group(1)
    obj_str = re.sub(r"//[^\n]*", "", obj_str)
    obj_str = re.sub(r",(\s*[}\]])", r"\1", obj_str)
    data = json.loads(obj_str)

    # 최소 크기로 직렬화 (compact)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_key(password, salt)
    aes = AESGCM(key)
    ct = aes.encrypt(nonce, payload, None)

    blob = base64.b64encode(salt + nonce + ct).decode("ascii")
    out = (
        f"// 포트폴리오 암호화본 (PBKDF2-SHA256 {ITERATIONS}회 + AES-256-GCM)\n"
        f"// 평문은 portfolio-data.plain.js (gitignored). 이 파일만 commit.\n"
        f"window.PORTFOLIO_ENCRYPTED = {json.dumps(blob)};\n"
        f"window.PBKDF2_ITERATIONS = {ITERATIONS};\n"
    )
    ENC_PATH.write_text(out, encoding="utf-8")
    print(f"암호화 완료: {ENC_PATH.name}  ({len(payload):,} → {len(blob):,} bytes base64)")


def decrypt(password: str) -> None:
    if not ENC_PATH.exists():
        sys.exit(f"암호화 파일 없음: {ENC_PATH.name}")
    text = ENC_PATH.read_text(encoding="utf-8")
    m = re.search(r'window\.PORTFOLIO_ENCRYPTED\s*=\s*"([^"]+)"', text)
    if not m:
        sys.exit("PORTFOLIO_ENCRYPTED 블록을 찾지 못함 (이미 평문일 수 있음)")
    blob = base64.b64decode(m.group(1))
    salt, nonce, ct = blob[:16], blob[16:28], blob[28:]
    key = derive_key(password, salt)
    aes = AESGCM(key)
    try:
        plain = aes.decrypt(nonce, ct, None)
    except Exception as e:
        sys.exit(f"복호화 실패 (비밀번호 오류 가능): {e}")
    data = json.loads(plain.decode("utf-8"))
    pretty = json.dumps(data, ensure_ascii=False, indent=2)
    out = (
        "// 포트폴리오 평문 데이터 (gitignored)\n"
        "// encrypt_data.py encrypt 로 portfolio-data.js 갱신\n"
        f"window.PORTFOLIO_DATA = {pretty};\n"
        "\n"
        "window.COUNTRY_NAMES = {\n"
        '  KR: "한국", US: "미국", CN: "중국", JP: "일본", TW: "대만",\n'
        '  IN: "인도", BR: "브라질", ZA: "남아공", SA: "사우디", MX: "멕시코",\n'
        '  DE: "독일", UK: "영국", FR: "프랑스", IT: "이탈리아", NL: "네덜란드",\n'
        '  CH: "스위스", AU: "호주", Other: "기타"\n'
        "};\n"
        'window.SIZE_NAMES   = { large: "대형주", mid: "중형주", small: "소형주" };\n'
        "window.FACTOR_NAMES = {\n"
        '  value: "Value", growth: "Growth", quality: "Quality", core: "Core",\n'
        '  thematic: "Thematic", dividend: "Dividend", esg: "ESG"\n'
        "};\n"
    )
    PLAIN_PATH.write_text(out, encoding="utf-8")
    print(f"복호화 완료: {PLAIN_PATH.name}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("encrypt", "decrypt"):
        sys.exit("사용: python encrypt_data.py [encrypt|decrypt] [password]")
    mode = sys.argv[1]
    pw = get_password(sys.argv[2] if len(sys.argv) > 2 else None)
    if mode == "encrypt":
        encrypt(pw)
    else:
        decrypt(pw)


if __name__ == "__main__":
    main()
