"""
포트폴리오 대시보드 로컬 웹 서버
- 같은 WiFi의 폰/태블릿에서 PC IP로 접속 가능
- 첫 실행 시 phone_qr.png 생성 (qrcode 패키지 있으면)
- 펀드매니저 탭 채팅용 /fm-chat 엔드포인트:
    로컬 Claude Code CLI(claude)를 호출해 응답을 스트리밍.
    Claude Code가 구독(Pro/Max)으로 로그인돼 있으면 토큰이 'API'가 아니라 '구독'에서 차감됨.
    (ANTHROPIC_API_KEY 환경변수가 있으면 API로 청구되므로, 이 서버는 서브프로세스 env에서 제거해
     구독 OAuth 인증을 강제한다.)
사용법:
    python serve.py [port]
설치(선택):
    pip install qrcode pillow
요건(구독 채팅):
    Claude Code CLI 설치 + `claude` 로 로그인(구독). 미설치 시 채팅은 API 키 모드로 폴백.
"""

import http.server
import socket
import sys
import io
import os
import json
import shutil
import subprocess
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

# 채팅에 사용할 모델 화이트리스트(임의 인자 주입 방지)
ALLOWED_MODELS = {
    "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
    "opus", "sonnet", "haiku",
}

# ▶ 추가 과금 방지(fail-closed): 서브프로세스 env에서 '구독이 아닌 청구'로 갈 수 있는 모든 경로 제거.
#   이걸 다 지우면 남는 인증은 /login 구독 OAuth 뿐 → API/클라우드로 청구되는 것이 구조적으로 불가능.
#   (인증이 없으면 호출은 '실패'할 뿐 유료 API로 폴백하지 않음.)
#   CLAUDE_CODE_OAUTH_TOKEN(구독 토큰)은 유지한다.
BILLING_ENV_STRIP = [
    "ANTHROPIC_API_KEY",        # 직접 API 청구
    "ANTHROPIC_AUTH_TOKEN",     # 게이트웨이/프록시 베어러
    "ANTHROPIC_BASE_URL",       # 커스텀 엔드포인트(프록시 과금)
    "ANTHROPIC_CUSTOM_HEADERS",
    "CLAUDE_CODE_USE_BEDROCK",  # AWS Bedrock 청구
    "CLAUDE_CODE_USE_VERTEX",   # GCP Vertex 청구
    "CLAUDE_CODE_USE_FOUNDRY",  # Azure Foundry 청구
    "ANTHROPIC_BEDROCK_BASE_URL", "ANTHROPIC_VERTEX_BASE_URL",
    "AWS_BEARER_TOKEN_BEDROCK", "ANTHROPIC_VERTEX_PROJECT_ID",
]


# ▶ 과금 backstop 설정 (환경변수로 조정 가능)
#   FM_BILLING_GUARD: "strict"(기본) = 유료 청구 env가 하나라도 있으면 채팅 거부 / "strip" = 제거만 하고 진행
#   FM_CHAT_DAILY_MAX: 하루 채팅 호출 상한(폭주·예기치 못한 사용 차단). 기본 200.
GUARD_MODE = os.environ.get("FM_BILLING_GUARD", "strict").lower()
try:
    DAILY_MAX = max(1, int(os.environ.get("FM_CHAT_DAILY_MAX", "200")))
except ValueError:
    DAILY_MAX = 200
# strict 모드에서 '하나라도 있으면 거부'할 진짜 유료 청구 활성화 변수
HARD_REFUSE_ENV = [
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
]
USAGE_FILE = HERE / ".fm_chat_usage.json"


def _today() -> str:
    import datetime as _dt
    return _dt.date.today().isoformat()


def usage_state() -> dict:
    try:
        d = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        if d.get("date") == _today():
            return {"date": d["date"], "count": int(d.get("count", 0))}
    except Exception:
        pass
    return {"date": _today(), "count": 0}


def usage_bump() -> int:
    s = usage_state()
    s["count"] += 1
    try:
        USAGE_FILE.write_text(json.dumps(s), encoding="utf-8")
    except Exception:
        pass
    return s["count"]


def settings_has_api_key_helper() -> bool:
    """전역/프로젝트 settings.json에 apiKeyHelper(설정 기반 API 키)가 있는지 — 있으면 구독보다 우선해 API 청구 위험.
    (--bare 로 settings를 무시하지만, 사용자에게 경고를 노출하기 위해 점검)."""
    paths = [
        Path.home() / ".claude" / "settings.json",
        HERE / ".claude" / "settings.json",
        HERE / ".claude" / "settings.local.json",
    ]
    for p in paths:
        try:
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(d, dict) and d.get("apiKeyHelper"):
                    return True
        except Exception:
            pass
    return False


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


def find_claude() -> str | None:
    """claude(Claude Code) 실행파일 탐색. CLAUDE_BIN > PATH > 알려진 설치경로."""
    env_bin = os.environ.get("CLAUDE_BIN")
    if env_bin and Path(env_bin).exists():
        return env_bin
    for name in ("claude", "claude.cmd", "claude.exe"):
        p = shutil.which(name)
        if p:
            return p
    home = Path.home()
    cands = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Claude" / "bin" / "claude.exe",
        Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
        home / ".local" / "bin" / "claude.exe",
        home / ".local" / "bin" / "claude",
        home / ".claude" / "local" / "claude",
    ]
    for c in cands:
        try:
            if c and str(c) and c.exists():
                return str(c)
        except Exception:
            pass
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def end_headers(self):
        # 캐시 비활성화: portfolio-data.js 갱신이 즉시 반영되도록
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        try:
            sys.stderr.write("  · " + (fmt % args) + "\n")
        except Exception:
            pass

    # ---------- 라우팅 ----------
    def do_GET(self):
        if self.path.split("?")[0] == "/fm-chat/health":
            return self._health()
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] == "/fm-chat":
            return self._chat()
        self.send_error(404, "Not Found")

    # ---------- 헬스체크 ----------
    def _health(self):
        claude = find_claude()
        risky = [k for k in BILLING_ENV_STRIP if os.environ.get(k)]
        body = json.dumps({
            "ok": True,
            "claude": bool(claude),
            "bin": claude or "",
            "api_key_env": bool(os.environ.get("ANTHROPIC_API_KEY")),
            # 청구 안전 진단: 감지돼도 서버가 서브프로세스 env에서 제거하므로 추가 과금은 막힘(참고용 표시)
            "risky_env": risky,
            "api_key_helper": settings_has_api_key_helper(),
            "oauth_token": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
            # 과금 backstop 상태
            "guard": GUARD_MODE,
            "daily_max": DAILY_MAX,
            "daily_used": usage_state()["count"],
            # strict 모드인데 유료 env가 있으면 채팅이 거부됨(=과금 불가)
            "blocked": (GUARD_MODE == "strict" and bool(risky)),
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    # ---------- 채팅(구독 차감) ----------
    def _chat(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self.send_error(400, "Bad JSON")

        system = (payload.get("system") or "").strip()
        context = (payload.get("context") or "").strip()
        messages = payload.get("messages") or []
        model = payload.get("model") or "claude-opus-4-8"
        if model not in ALLOWED_MODELS:
            model = "claude-opus-4-8"

        claude = find_claude()
        if not claude:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self._w("⚠ Claude Code CLI(`claude`)를 찾지 못했습니다.\n"
                    "구독 차감 채팅은 Claude Code 설치 + 로그인이 필요합니다.\n"
                    "설치 후 `claude` 로 로그인하거나, 우측 상단에서 'API 키' 모드로 전환하세요.\n"
                    "(설치되어 있다면 CLAUDE_BIN 환경변수로 경로를 지정할 수 있습니다.)")
            return

        # ── Backstop 1: strict 모드 — 유료 청구 env가 하나라도 있으면 아예 실행 거부(과금 원천 차단) ──
        present = [k for k in HARD_REFUSE_ENV if os.environ.get(k)]
        if GUARD_MODE == "strict" and present:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self._w("🛑 과금 안전장치(strict)로 채팅을 거부했습니다.\n"
                    "유료 청구 가능 환경변수가 감지됨: " + ", ".join(present) + "\n"
                    "이 터미널에서 해당 변수를 해제(예: PowerShell `Remove-Item Env:ANTHROPIC_API_KEY`) 후 "
                    "serve.py를 다시 실행하세요.\n"
                    "구독으로만 청구되는 게 확실하면 FM_BILLING_GUARD=strip 으로 우회할 수 있습니다(권장하지 않음).")
            return

        # ── Backstop 2: 하루 호출 상한(폭주·예기치 못한 사용 차단) ──
        used = usage_state()["count"]
        if used >= DAILY_MAX:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self._w("🛑 오늘 채팅 한도(%d회)에 도달했습니다. 폭주/예상치 못한 사용을 막기 위한 상한입니다.\n"
                    "내일 자동 초기화되며, 상한을 바꾸려면 FM_CHAT_DAILY_MAX 환경변수로 조정하세요." % DAILY_MAX)
            return
        usage_bump()

        # 대화 → 단일 프롬프트(stdin). 컨텍스트는 길어서 stdin으로(시스템/인자 길이 제한 회피).
        convo = []
        for m in messages[:-1]:
            who = "사용자" if m.get("role") == "user" else "Claude(직전 답변)"
            convo.append("[%s]\n%s" % (who, m.get("content", "")))
        last = messages[-1].get("content", "") if messages else ""
        prompt = "<CONTEXT>\n" + context + "\n</CONTEXT>\n\n"
        if convo:
            prompt += "=== 이전 대화 ===\n" + "\n\n".join(convo) + "\n\n"
        prompt += "=== 현재 질문 ===\n" + last

        # 구독 OAuth 강제(fail-closed): 유료 청구 경로 env 전부 제거
        env = os.environ.copy()
        for k in BILLING_ENV_STRIP:
            env.pop(k, None)

        cmd = [
            # 주의: 과거엔 --bare로 settings(apiKeyHelper) 무시했으나, claude CLI v2.1.x에서
            # --bare가 구독 OAuth 인증까지 무력화('Not logged in')시키는 문제가 있어 제거.
            # apiKeyHelper/유료경로 방어는 BILLING_ENV_STRIP + 아래 apiKeySource 런타임 가드로 대체.
            claude, "-p",
            "--append-system-prompt", system,
            "--model", model,
            "--allowedTools", "WebSearch,WebFetch",  # 최신 주가·컨센서스·뉴스 조회용 웹 검색 허용(읽기 전용 도구만)
            "--output-format", "stream-json",
            "--verbose", "--include-partial-messages",
        ]

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env, text=True,
                encoding="utf-8", errors="replace", cwd=str(HERE),
            )
        except Exception as e:
            self._w("⚠ Claude Code 실행 실패: %s" % e)
            return

        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception:
            pass

        sent = False
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                t = ev.get("type")
                if t == "system" and ev.get("subtype") == "init":
                    # 런타임 안전장치: 인증 출처가 API 키 계열이면 즉시 중단(추가 과금 방지)
                    src = str(ev.get("apiKeySource", "")).lower()
                    if src and src not in ("none", "", "login", "subscription"):
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        self._w("⚠ 안전 중단: 인증 출처가 '" + src + "' 로 감지됨(구독이 아닐 수 있음).\n"
                                "추가 과금을 막기 위해 호출을 중단했습니다. `claude` 가 구독으로 로그인됐는지 확인하세요.")
                        return
                    continue
                if t == "stream_event":
                    e = ev.get("event", {})
                    if e.get("type") == "content_block_delta":
                        dl = e.get("delta", {})
                        if dl.get("type") == "text_delta" and dl.get("text"):
                            sent = True
                            if not self._w(dl["text"]):
                                break
                elif t == "assistant" and not sent:
                    for blk in (ev.get("message", {}) or {}).get("content", []):
                        if blk.get("type") == "text" and blk.get("text"):
                            sent = True
                            self._w(blk["text"])
                elif t == "result" and not sent:
                    if ev.get("result"):
                        sent = True
                        self._w(str(ev["result"]))
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        if not sent:
            err = ""
            try:
                err = (proc.stderr.read() or "")[:600]
            except Exception:
                pass
            self._w("⚠ 응답을 받지 못했습니다. Claude Code 로그인/플랜 상태를 확인하세요.\n" + err)

    def _w(self, s: str) -> bool:
        try:
            self.wfile.write(s.encode("utf-8"))
            self.wfile.flush()
            return True
        except Exception:
            return False


def make_qr(url: str):
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
    claude = find_claude()

    print("\n" + "=" * 60)
    print("  포트폴리오 대시보드 서버")
    print("=" * 60)
    print(f"  PC:    {url_pc}")
    print(f"  Phone: {url_phone}  ← 같은 WiFi에서 접속")
    if qr_path:
        print(f"  QR:    {qr_path}  ← 폰 카메라로 스캔")
    else:
        print("  QR:    (선택) pip install qrcode pillow")
    if claude:
        present = [k for k in HARD_REFUSE_ENV if os.environ.get(k)]
        print(f"  펀드매니저 채팅: 구독 차감 가능 (claude={claude})")
        print(f"  과금 backstop: guard={GUARD_MODE} · 하루상한={DAILY_MAX}회 · 오늘 {usage_state()['count']}회")
        if present:
            if GUARD_MODE == "strict":
                print(f"    🛑 유료청구 env 감지 {present} → strict로 채팅 거부됨(과금 불가). 해제 후 재실행하세요.")
            else:
                print(f"    ⚠ 유료청구 env 감지 {present} → strip로 제거 후 진행(구독 청구).")
    else:
        print("  펀드매니저 채팅: Claude Code 미발견 → API 키 모드로 폴백")
    print("\n  Ctrl+C 로 종료\n")

    # 채팅이 길게 도는 동안 정적 파일 서빙이 막히지 않도록 멀티스레드
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n서버 종료")


if __name__ == "__main__":
    main()
