"""
포트폴리오 대시보드 로컬 웹 서버
- 같은 WiFi의 폰/태블릿에서 PC IP로 접속 가능
- 첫 실행 시 phone_qr.png 생성 (qrcode 패키지 있으면)
사용법:
    python serve.py [port]
설치(선택):
    pip install qrcode pillow
"""

import http.server
import socketserver
import socket
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


def lan_ip() -> str:
    """라우터를 향한 외부 인터페이스의 LAN IP"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def end_headers(self):
        # 캐시 비활성화: portfolio-data.js 갱신이 즉시 반영되도록
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        # 접속 로그는 한 줄로 짧게
        try:
            sys.stderr.write("  · " + (fmt % args) + "\n")
        except Exception:
            pass


def make_qr(url: str) -> Path | None:
    try:
        import qrcode  # type: ignore
        img = qrcode.make(url)
        path = HERE / "phone_qr.png"
        img.save(path)
        return path
    except ImportError:
        return None


def main():
    ip = lan_ip()
    url_pc = f"http://localhost:{PORT}/portfolio.html"
    url_phone = f"http://{ip}:{PORT}/portfolio.html"

    qr_path = make_qr(url_phone)

    print("\n" + "=" * 60)
    print("  포트폴리오 대시보드 서버")
    print("=" * 60)
    print(f"  PC:    {url_pc}")
    print(f"  Phone: {url_phone}  ← 같은 WiFi에서 접속")
    if qr_path:
        print(f"  QR:    {qr_path}  ← 폰 카메라로 스캔")
    else:
        print("  QR:    (선택) pip install qrcode pillow")
    print("\n  Ctrl+C 로 종료\n")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n서버 종료")


if __name__ == "__main__":
    main()
