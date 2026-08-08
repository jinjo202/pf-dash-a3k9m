# -*- coding: utf-8 -*-
"""
send_email_cio.py — fm-cio.js의 최신 CIO 데일리 의견을 메일로 발송.

generate_cio.py가 만든 fm-cio.js의 첫 엔트리(entries[0])를 HTML 메일로 렌더한다.
대시보드 fm.html/agent.html과 같은 데이터라 화면을 안 열어도 매일 받아볼 수 있다.

⚠ 보유 대조는 하지 않는다. 대시보드는 복호화된 실제 보유와 대조해 '유지·확대/신규 편입'
   라벨을 붙이지만, 메일은 평문으로 나가므로 보유 정보를 넣지 않는다(public repo·메일 유출
   리스크). 방향성(lean: 강세/약세)만 그대로 전달하고, 보유 대조는 대시보드에서 보라고 안내.

사용:
  python briefing/send_email_cio.py            # 발송
  python briefing/send_email_cio.py --dry-run  # 렌더만(발송 안 함)
  python briefing/send_email_cio.py --test     # 제목에 [테스트]
  python briefing/send_email_cio.py --skip-if-sent  # 같은 (as_of,slot) 이미 보냈으면 종료

env: GMAIL_SENDER, GMAIL_APP_PASSWORD (아시아/미국 시황 메일과 동일)
"""
import html as _html
import json
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CIO_JS = os.path.join(REPO, "fm-cio.js")
STATE = os.path.join(REPO, "cio-mail-state.json")   # 중복발송 방지(gitignored)

RECIPIENTS = ["jinyoung22.jo@samsung.com", "jin.jo202@gmail.com"]
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465

DASH_URL = "https://jinjo202.github.io/pf-dash-a3k9m/fm.html"

VERDICT_KO = {"pos": ("긍정", "#16794a"), "neg": ("부정", "#b91c1c"),
              "watch": ("주시", "#9a6700")}
NATURE_KO = {"technical": "기술적·수급", "fundamental": "펀더멘털", "mixed": "혼재"}
LEAN_KO = {"bullish": ("강세 방향", "#16794a"), "bearish": ("약세 방향", "#b91c1c")}


def esc(s):
    return _html.escape(str(s or ""))


def load_entry():
    with open(CIO_JS, encoding="utf-8") as f:
        t = f.read()
    m = re.search(r"window\.FM_CIO\s*=\s*(\{.*\})\s*;", t, re.S)
    if not m:
        sys.exit("fm-cio.js 파싱 실패")
    entries = (json.loads(m.group(1)) or {}).get("entries") or []
    if not entries:
        sys.exit("fm-cio.js에 엔트리 없음")
    return entries[0]


def _p(txt, style=""):
    return '<p style="margin:0 0 10px;line-height:1.65;%s">%s</p>' % (style, txt)


def build_html(e):
    slot_ko = "미국장 마감 반영" if e.get("slot") == "us_close" else "아시아장 마감 반영"
    # MIME 헤더에도 utf-8을 주지만, 본문 meta를 우선하는 클라이언트가 있어 함께 선언한다.
    P = ['<meta charset="utf-8">',
         '<div style="max-width:680px;font-family:-apple-system,\'Malgun Gothic\',sans-serif;'
         'font-size:14px;color:#1a1a1a">']
    P.append('<h2 style="margin:0 0 4px;font-size:18px">🧭 CIO 데일리 의견</h2>')
    P.append('<div style="color:#666;font-size:12px;margin-bottom:14px">%s · %s</div>'
             % (esc(e.get("as_of")), esc(slot_ko)))

    if e.get("headline"):
        P.append('<div style="background:#f4f6f8;border-left:4px solid #2f6feb;padding:10px 14px;'
                 'margin:0 0 16px;font-weight:700;line-height:1.6">%s</div>' % esc(e["headline"]))

    chain = e.get("chain") or []
    if chain:
        P.append('<h3 style="font-size:15px;margin:18px 0 8px">🔗 이슈 체인</h3>')
        for c in chain:
            ko, col = VERDICT_KO.get(c.get("verdict"), ("주시", "#666"))
            P.append('<div style="border:1px solid #e3e6ea;border-radius:8px;padding:10px 12px;'
                     'margin-bottom:8px">'
                     '<div style="margin-bottom:4px">'
                     '<span style="background:%s;color:#fff;border-radius:4px;padding:1px 7px;'
                     'font-size:11px;font-weight:700">%s</span> '
                     '<span style="color:#666;font-size:11px">%s</span> '
                     '<b>%s</b></div>' % (col, ko, esc(NATURE_KO.get(c.get("nature"), "")),
                                          esc(c.get("issue"))))
            if c.get("read"):
                P.append('<div style="color:#333;line-height:1.6;font-size:13px">%s</div>'
                         % esc(c["read"]))
            if c.get("action"):
                P.append('<div style="color:#2f6feb;font-size:13px;margin-top:4px">→ %s</div>'
                         % esc(c["action"]))
            P.append('</div>')

    pos = e.get("positioning") or {}
    ew = pos.get("equity_weight") or {}
    if ew:
        P.append('<h3 style="font-size:15px;margin:18px 0 8px">⚖️ 포지셔닝</h3>')
        P.append(_p("주식비중 <b>%s</b> — %s" % (esc(ew.get("stance")), esc(ew.get("reason")))))
    for k, lbl in (("country", "국가"), ("sector", "섹터")):
        if pos.get(k):
            P.append(_p("<b>%s</b> — %s" % (lbl, esc(pos[k]))))

    trades = pos.get("trades") or []
    if trades:
        P.append('<h3 style="font-size:15px;margin:18px 0 8px">🎯 방향성 아이디어</h3>')
        P.append('<div style="font-size:12px;color:#666;margin-bottom:6px">'
                 '보유 여부 대조(유지·확대/신규 편입)는 보안상 메일에 넣지 않습니다 — '
                 '<a href="%s">대시보드</a>에서 확인하세요.</div>' % DASH_URL)
        P.append('<ul style="margin:0;padding-left:18px;line-height:1.7">')
        for t in trades:
            ko, col = LEAN_KO.get(t.get("lean"), ("방향 미상", "#666"))
            P.append('<li><span style="color:%s;font-weight:700">%s</span> '
                     '<b>%s</b> <span style="color:#666;font-size:12px">%s</span> — %s</li>'
                     % (col, ko, esc(t.get("name")), esc(t.get("ticker")), esc(t.get("reason"))))
        P.append('</ul>')

    wl = e.get("watchlist") or []
    if wl:
        P.append('<h3 style="font-size:15px;margin:18px 0 8px">🔍 부진 ETF 점검</h3>'
                 '<ul style="margin:0;padding-left:18px;line-height:1.7">')
        for w in wl:
            bits = [x for x in [w.get("why_lagging"), w.get("hold_thesis")] if x]
            P.append('<li><b>%s</b> <span style="color:#666;font-size:12px">%s</span> — %s</li>'
                     % (esc(w.get("name") or w.get("ticker")), esc(w.get("verdict")),
                        esc(" / ".join(bits))))
        P.append('</ul>')

    if e.get("technicals_read"):
        P.append('<h3 style="font-size:15px;margin:18px 0 8px">📉 기술적·수급·유동성</h3>')
        P.append(_p(esc(e["technicals_read"])))

    P.append('<div style="margin-top:22px;padding-top:12px;border-top:1px solid #e3e6ea;'
             'color:#888;font-size:11px;line-height:1.6">'
             'generate_cio.py 자동 생성 · 투자 판단의 참고자료이며 투자권유가 아닙니다.<br>'
             '전체 화면(보유 대조·ETF factsheet·백테스트): <a href="%s">%s</a></div>'
             % (DASH_URL, DASH_URL))
    P.append('</div>')
    return "".join(P)


def build_plain(e):
    L = ["[CIO 데일리 의견] %s (%s)" % (e.get("as_of"), e.get("slot")), ""]
    if e.get("headline"):
        L += [e["headline"], ""]
    for c in e.get("chain") or []:
        L.append("- [%s] %s" % (VERDICT_KO.get(c.get("verdict"), ("주시",))[0], c.get("issue")))
        if c.get("read"):
            L.append("  " + c["read"])
    pos = e.get("positioning") or {}
    for t in pos.get("trades") or []:
        L.append("* %s %s (%s) — %s" % (LEAN_KO.get(t.get("lean"), ("방향 미상",))[0],
                                        t.get("name"), t.get("ticker"), t.get("reason")))
    L += ["", "대시보드: " + DASH_URL]
    return "\n".join(L)


def _state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    argv = sys.argv[1:]
    dry, test = "--dry-run" in argv, "--test" in argv
    skip_if_sent = "--skip-if-sent" in argv

    e = load_entry()
    key = "%s|%s" % (e.get("as_of"), e.get("slot"))
    if skip_if_sent and _state().get("last_sent") == key:
        print("이미 발송함 (%s) — 스킵" % key)
        return 0

    bom = chr(0xFEFF)
    sender = (os.environ.get("GMAIL_SENDER") or "").replace(bom, "").strip()
    pw = (os.environ.get("GMAIL_APP_PASSWORD") or "").replace(bom, "").strip()
    if not sender or not pw:
        sys.exit("env GMAIL_SENDER / GMAIL_APP_PASSWORD 없음")

    slot_ko = "미국장" if e.get("slot") == "us_close" else "아시아장"
    subject = "CIO 데일리 의견 %s (%s)" % (e.get("as_of"), slot_ko)
    if test:
        subject = "[테스트] " + subject

    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Subject"] = Header(subject, "utf-8")
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(build_plain(e), "plain", "utf-8"))
    msg.attach(MIMEText(build_html(e), "html", "utf-8"))

    if dry:
        print("FROM:", sender, "\nTO:", RECIPIENTS, "\nSUBJECT:", subject)
        print("HTML_BYTES:", len(build_html(e)), "| 체인", len(e.get("chain") or []),
              "| 트레이드", len((e.get("positioning") or {}).get("trades") or []))
        return 0

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as s:
        s.login(sender, pw)
        s.sendmail(sender, RECIPIENTS, msg.as_string())
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"last_sent": key, "at": datetime.now().isoformat(timespec="seconds")},
                  f, ensure_ascii=False)
    print("발송 완료: %s → %d명" % (subject, len(RECIPIENTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
