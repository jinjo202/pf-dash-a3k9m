# -*- coding: utf-8 -*-
"""
아시아 시황: 실제 SMTP 발송 스크립트.
브리핑(paragraphs)을 바탕체 HTML 본문 + 개조식 보고서(.docx) 첨부로
Gmail SMTP(SSL 465) 를 통해 두 수신자에게 발송한다.

자격증명: 환경변수
  GMAIL_SENDER         발신 Gmail 주소
  GMAIL_APP_PASSWORD   16자리 Google 앱 비밀번호 (공백 없이)

사용법:
  python send_email_asia.py <archive.js> [as_of] [--dry-run] [--test]
"""
import sys, os, re, html, smtplib, ssl, subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formatdate
from datetime import datetime

# 같은 디렉터리의 make_docx_b64.py 재사용.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_docx_b64 import load_briefings, build_docx_bytes, minify_docx

RECIPIENTS = ["jinyoung22.jo@samsung.com", "jin.jo202@gmail.com"]
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def esc(s):
    return html.escape(s, quote=False)


def md_from(as_of):
    try:
        d = datetime.strptime(as_of, "%Y-%m-%d")
        return "%d/%d" % (d.month, d.day)
    except (TypeError, ValueError):
        return ""


def fetch_samsung_trio(as_of):
    if not as_of:
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    helper = os.path.join(here, "get_samsung_trio.py")
    try:
        result = subprocess.run(
            [sys.executable, helper, as_of],
            capture_output=True, timeout=45,
        )
        if result.returncode != 0:
            return None
        out = result.stdout.decode("utf-8", errors="replace").strip()
        return out or None
    except Exception:
        return None


def _is_korea_market_paragraph(t):
    if not t:
        return False
    if t.startswith("* ") or t.startswith("※ "):
        return False
    has_kr = ("코스피" in t) or ("코스닥" in t)
    if not has_kr:
        return False
    other = ("닛케이" in t) or ("상해" in t) or ("항셍" in t) or ("선전" in t) or ("H주" in t)
    return not other


def inject_samsung_trio(brief, trio_text):
    if not trio_text:
        return brief
    paragraphs = list(brief.get("paragraphs") or [])
    for p in paragraphs:
        t = p or ""
        if "(전자 " in t or "(한국 휴장)" in t:
            return brief
    target_idx = -1
    for i, p in enumerate(paragraphs):
        if _is_korea_market_paragraph((p or "").strip()):
            target_idx = i
            break
    if target_idx < 0:
        for i, p in enumerate(paragraphs):
            t = (p or "").strip()
            if t and not t.startswith("* ") and not t.startswith("※ "):
                if ("코스피" in t) or ("코스닥" in t):
                    target_idx = i
                    break
    if target_idx < 0:
        return brief
    new_paragraphs = list(paragraphs)
    t = (new_paragraphs[target_idx] or "").strip()
    if not t.endswith("."):
        t = t + "."
    new_paragraphs[target_idx] = t + " (" + trio_text + ")"
    brief = dict(brief)
    brief["paragraphs"] = new_paragraphs
    return brief


def split_sentences(text):
    parts = re.split(r'(?<=[^\d])\.\s+', text)
    out = []
    for i, p in enumerate(parts):
        p = p.strip()
        if not p:
            continue
        if i < len(parts) - 1:
            out.append(p + '.')
        else:
            out.append(p)
    return out


def build_html(brief):
    md = md_from(brief.get("as_of"))
    paragraphs = [p.strip() for p in (brief.get("paragraphs") or []) if p and p.strip()]

    BODY = ('font-family:굴림,sans-serif;font-size:12pt;line-height:145%;'
            'margin-left:0px;margin-bottom:10.66px')
    INNER_BLACK = 'background:transparent;font-family:바탕체,serif;color:black'
    INNER_BLUE = ('background:transparent;font-size:11pt;line-height:145%;'
                  'font-family:바탕체,serif;color:blue')
    TITLE_FONT = "'맑은  고딕',sans-serif"

    def styled_blank():
        return ('<p style="' + BODY + '">'
                '<span style="background-color:transparent"><br></span></p>')

    def body_p(text):
        return ('<p style="' + BODY + '">'
                '<span style="' + INNER_BLACK + '">' + esc(text) + '</span></p>')

    def blue_p(text):
        return ('<p style="' + BODY + '">'
                '<span style="' + INNER_BLUE + '">' + esc(text) + '</span></p>')

    parts = []
    parts.append('<div style="max-width:640px;font-family:굴림,sans-serif">')

    parts.append(
        '<p>'
        '<span style="font-weight:bold;font-family:' + TITLE_FONT + ';font-size:13.3333px">Title</span>'
        '<span style="font-family:' + TITLE_FONT + ';font-size:13.3333px">  : 아시아 시황(' + md + ')</span>'
        '</p>'
    )
    parts.append('<p><br></p>')

    n = len(paragraphs)
    for i, t in enumerate(paragraphs):
        if t.startswith("* "):
            parts.append(blue_p("※ " + t[2:]))
        elif t.startswith("※ "):
            parts.append(body_p(t))
        else:
            sentences = split_sentences(t)
            if not sentences:
                continue
            for s in sentences:
                parts.append(body_p(s))
        if i + 1 < n:
            nxt = paragraphs[i + 1]
            if not (nxt.startswith("* ") or nxt.startswith("※ ")):
                parts.append(styled_blank())
        else:
            parts.append(styled_blank())

    parts.append(body_p("감사합니다."))
    parts.append('</div>')

    return ''.join(parts)


def build_plain(brief):
    lines = []
    for raw in (brief.get("paragraphs") or []):
        t = ("" if raw is None else str(raw)).strip()
        if not t:
            continue
        if t.startswith("* "):
            lines.append("※ " + t[2:])
        else:
            lines.append(t)
    lines.append("")
    lines.append("감사합니다.")
    lines.append("")
    lines.append("(첨부: 개조식 보고서 Word 파일)")
    return "\n".join(lines)


def build_message(brief, sender, test=False):
    md = md_from(brief.get("as_of"))
    subject = "아시아 시황(%s)" % md
    if test:
        subject = "[테스트] " + subject

    docx_bytes = minify_docx(build_docx_bytes(brief))

    trio = fetch_samsung_trio(brief.get("as_of"))
    brief_for_email = inject_samsung_trio(brief, trio) if trio else brief

    html_body = build_html(brief_for_email)
    plain_body = build_plain(brief_for_email)

    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Subject"] = Header(subject, "utf-8")
    msg["Date"] = formatdate(localtime=True)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    att = MIMEApplication(
        docx_bytes,
        _subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    fname = "아시아시황_%s.docx" % (brief.get("as_of") or "")
    att.add_header("Content-Disposition", "attachment",
                   filename=("utf-8", "", fname))
    msg.attach(att)
    return msg, subject, len(docx_bytes), len(html_body)


def main():
    raw = sys.argv[1:]
    dry = "--dry-run" in raw
    test = "--test" in raw
    args = [a for a in raw if not a.startswith("--")]
    if not args:
        sys.stderr.write("usage: send_email_asia.py <archive.js> [as_of] [--dry-run] [--test]\n")
        sys.exit(2)
    js_path = args[0]
    as_of = args[1] if len(args) > 1 else None

    _bom = chr(0xFEFF)
    sender = (os.environ.get("GMAIL_SENDER") or "").replace(_bom, "").strip()
    password = (os.environ.get("GMAIL_APP_PASSWORD") or "").replace(_bom, "").strip()
    if not sender or not password:
        sys.stderr.write("env GMAIL_SENDER / GMAIL_APP_PASSWORD missing\n")
        sys.exit(3)

    arr = load_briefings(js_path)
    if not arr:
        sys.stderr.write("empty briefings archive: " + js_path + "\n")
        sys.exit(1)
    brief = arr[0]
    if as_of:
        for b in arr:
            if b.get("as_of") == as_of:
                brief = b
                break

    msg, subject, docx_len, html_len = build_message(brief, sender, test=test)

    if dry:
        print("FROM:", sender)
        print("TO:", RECIPIENTS)
        print("SUBJECT:", subject)
        print("DOCX_BYTES:", docx_len)
        print("HTML_BYTES:", html_len)
        return

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as s:
            s.login(sender, password)
            s.sendmail(sender, RECIPIENTS, msg.as_string())
    except Exception as e:
        sys.stderr.write("SMTP failure: %s\n" % e)
        sys.exit(4)

    print("sent:", subject, "->", RECIPIENTS)


if __name__ == "__main__":
    main()
