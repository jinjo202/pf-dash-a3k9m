# -*- coding: utf-8 -*-
"""
미국·유럽 시황: SMTP 발송.
양식: '일일 금융시장 동향(M/D)'. 한국어 본문.

  - "_ {본문}" 으로 시작하는 paragraph → 본문 전체 bold + underline
  - "* " 인덱스 라인 → "* " 그대로, 파란 12pt + letter-spacing:-0.4pt
  - Samsung Trio inject 없음

자격증명: GMAIL_SENDER + GMAIL_APP_PASSWORD

사용법:
  python send_email_us.py <archive.js> [as_of] [--dry-run] [--test]
"""
import sys, os, re, html, smtplib, ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formatdate
from datetime import datetime

# 같은 디렉터리의 make_docx_b64.py 재사용 (개조식 docx 포맷 동일).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_docx_b64 import load_briefings, build_docx_bytes, minify_docx  # noqa: E402

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


def needs_blank_after(idx, paragraphs):
    if idx + 1 >= len(paragraphs):
        return False
    nxt = paragraphs[idx + 1]
    return not (nxt.startswith("* ") or nxt.startswith("※ "))


def build_html(brief):
    md = md_from(brief.get("as_of"))
    paragraphs = [p.strip() for p in (brief.get("paragraphs") or []) if p and p.strip()]

    BODY = ('box-sizing:content-box;font-family:굴림,sans-serif;color:rgb(0,0,0);'
            'font-size:12pt;line-height:1.5;font-weight:400;margin:5px 0px 10.66px;padding:0px')
    INNER_BLACK = ('box-sizing:content-box;font-family:바탕체,serif;color:black;'
                   'margin:0px;padding:0px')
    INNER_BOLD_U = ('text-decoration:underline;font-weight:bold;box-sizing:content-box;'
                    'font-family:바탕체,serif;color:black;margin:0px;padding:0px')
    INNER_BLUE = ('box-sizing:content-box;font-family:바탕체,serif;color:blue;'
                  'letter-spacing:-0.4pt;margin:0px;padding:0px')
    TITLE_FONT = "'맑은  고딕',sans-serif"

    def styled_blank():
        return ('<p style="' + BODY + '"><span style="box-sizing:content-box">'
                '<br></span></p>')

    def make_p(text, inner_style):
        return ('<p style="' + BODY + '">'
                '<span style="' + inner_style + '">' + esc(text) + '</span></p>')

    parts = []
    parts.append('<div style="max-width:640px;font-family:굴림,sans-serif">')

    parts.append(
        '<p>'
        '<span style="font-weight:bold;font-family:' + TITLE_FONT + ';font-size:13.3333px">Title</span>'
        '<span style="font-family:' + TITLE_FONT + ';font-size:13.3333px">  : 일일 금융시장 동향(' + md + ')</span>'
        '</p>'
    )
    parts.append('<p><br></p>')

    n = len(paragraphs)
    for i, t in enumerate(paragraphs):
        if t.startswith("_ "):
            inner_text = t[2:]
            sentences = split_sentences(inner_text)
            if not sentences:
                continue
            for s in sentences:
                parts.append(make_p(s, INNER_BOLD_U))
        elif t.startswith("* "):
            parts.append(make_p(t, INNER_BLUE))
        elif t.startswith("※ "):
            parts.append(make_p(t, INNER_BLACK))
        else:
            sentences = split_sentences(t)
            if not sentences:
                continue
            for s in sentences:
                parts.append(make_p(s, INNER_BLACK))

        if needs_blank_after(i, paragraphs):
            parts.append(styled_blank())

    parts.append('</div>')
    return ''.join(parts)


def build_plain(brief):
    lines = []
    for raw in (brief.get("paragraphs") or []):
        t = ("" if raw is None else str(raw)).strip()
        if not t:
            continue
        if t.startswith("_ "):
            t = t[2:]
        lines.append(t)
    lines.append("")
    lines.append("(첨부: 개조식 보고서 Word 파일)")
    return "\n".join(lines)


def build_message(brief, sender, test=False):
    md = md_from(brief.get("as_of"))
    subject = "일일 금융시장 동향(%s)" % md
    if test:
        subject = "[테스트] " + subject

    docx_bytes = minify_docx(build_docx_bytes(brief))
    html_body = build_html(brief)
    plain_body = build_plain(brief)

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
    fname = "일일금융시장동향_%s.docx" % (brief.get("as_of") or "")
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
        sys.stderr.write("usage: send_email_us.py <archive.js> [as_of] [--dry-run] [--test]\n")
        sys.exit(2)
    js_path = args[0]
    as_of = args[1] if len(args) > 1 else None

    sender = os.environ.get("GMAIL_SENDER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
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
