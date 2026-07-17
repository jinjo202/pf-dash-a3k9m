"""Gmail SMTP 발송 (stdlib만 사용 — Selenium/PDF 불필요).

dart-mail-sender/browser_email_sender.py 의 SMTP_SSL 방식을 그대로 따름.
앱 비밀번호(16자리)는 .env 에서 주입한다.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from dart_client import Disclosure


def send_email(
    smtp_user: str,
    smtp_pass: str,
    sender: str,
    recipients: list[str],
    subject: str,
    html_body: str,
    attachment_path: str | None = None,
) -> bool:
    """Gmail SMTP_SSL(465)로 HTML 메일 발송. attachment_path 있으면 첨부. 성공 시 True."""
    if not recipients:
        print("   ❌ [SMTP] 수신자가 비어 있음")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                fn = os.path.basename(attachment_path)
                # 파일명 한글 → RFC2231 인코딩
                part.add_header("Content-Disposition", "attachment", filename=fn)
                msg.attach(part)
                print(f"   📎 첨부: {fn}")
            except Exception as fe:
                print(f"   ⚠️ 첨부 실패(메일은 발송): {fe}")

        server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
        server.login(smtp_user, smtp_pass)
        server.sendmail(sender, recipients, msg.as_string())
        server.quit()
        print(f"   ✅ [SMTP] 발송 성공 → 수신자 {len(recipients)}명")
        return True
    except Exception as e:
        print(f"   ❌ [SMTP] 발송 실패: {e}")
        return False


def build_subject(d: Disclosure) -> str:
    # DART report_nm은 뒤쪽 공백으로 패딩돼 옴 → strip 필수
    return f"[배당공시] {d.corp_name.strip()} - {d.report_nm.strip()}"


def build_etf_subject(etf_name: str, report_nm: str) -> str:
    return f"[ETF분배] {etf_name} - {report_nm}"


def build_overseas_subject(e: dict) -> str:
    return f"[해외ETF분배] {e['name']} - 1주당 {e['amount']}"


def build_overseas_body(e: dict) -> str:
    th = ("text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;"
          "font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px")
    td = "padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef"
    pay_note = " (예상)" if e.get("pay_estimated") else ""
    return f"""\
<div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);overflow:hidden">
  <div style="background:linear-gradient(135deg,#00695c,#00897b);color:#fff;padding:24px 32px">
    <h1 style="margin:0;font-size:20px;font-weight:600">💵 해외 ETF 분배금 확정</h1>
    <div style="display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:20px;font-size:12px;margin-top:8px">보유 해외 ETF 분배 알림</div>
  </div>
  <div style="padding:32px">
    <p style="color:#495057;font-size:15px">보유 해외 ETF의 분배가 확정(배당락)되었습니다.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr><th style="{th}">종목</th><td style="{td}"><strong>{e['name']}</strong> ({e['sym']})</td></tr>
      <tr><th style="{th}">1주당 분배금</th><td style="{td};font-weight:700;color:#00695c">{e['amount']}</td></tr>
      <tr><th style="{th}">배당락일(ex)</th><td style="{td}">{e['ex_date']}</td></tr>
      <tr><th style="{th}">지급 예정일</th><td style="{td};font-weight:600">{e['pay_date']}{pay_note}</td></tr>
    </table>
    <p style="color:#868e96;font-size:12px;margin-top:8px">※ 지급일 '예상'은 배당락 + 통상 지급주기 추정치입니다(발행사별 상이).</p>
  </div>
  <div style="padding:16px 32px;background:#f8f9fa;font-size:12px;color:#868e96;text-align:center">
    이 메일은 배당·분배 공시 모니터링 시스템에서 자동 발송되었습니다.
  </div>
</div>"""


def build_reminder_subject(r: dict, stage: str) -> str:
    when = "내일" if stage == "d1" else "오늘"
    tag = "D-1" if stage == "d1" else "기준일"
    amt = f" ({r.get('amount')})" if r.get("amount") and r["amount"] != "-" else ""
    return f"[배당 {tag}] {when} {r.get('name')} 배당기준일{amt}"


def build_reminder_body(r: dict, stage: str) -> str:
    when = "내일이" if stage == "d1" else "오늘이"
    color = "#e65100" if stage == "d1" else "#c62828"
    th = ("text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;"
          "font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px")
    td = "padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef"
    pay = r.get("pay_date") or "-"
    amt = r.get("amount") or "-"
    return f"""\
<div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);overflow:hidden">
  <div style="background:linear-gradient(135deg,{color},#ff8f00);color:#fff;padding:24px 32px">
    <h1 style="margin:0;font-size:20px;font-weight:600">⏰ {when} {r.get('name')} 배당기준일입니다</h1>
    <div style="display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:20px;font-size:12px;margin-top:8px">배당 리마인드 ({'D-1' if stage=='d1' else '당일'})</div>
  </div>
  <div style="padding:32px">
    <div style="background:#fff3e0;border-left:4px solid {color};padding:16px;border-radius:4px;margin-bottom:24px;color:{color};font-size:14px;font-weight:600;line-height:1.6">
      ⚠️ 배당을 받으려면 <b>배당기준일</b>까지 주식을 보유해야 합니다. 권리 확정 여부를 점검하세요.
    </div>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr><th style="{th}">종목</th><td style="{td}"><strong>{r.get('name')}</strong> ({r.get('code')})</td></tr>
      <tr><th style="{th}">배당기준일</th><td style="{td};color:{color};font-weight:700">{r.get('record_date')} ({'내일' if stage=='d1' else '오늘'})</td></tr>
      <tr><th style="{th}">1주당 배당금</th><td style="{td};font-weight:700;color:#1a237e">{amt}</td></tr>
      <tr><th style="{th}">지급 예정일</th><td style="{td}">{pay}</td></tr>
    </table>
  </div>
  <div style="padding:16px 32px;background:#f8f9fa;font-size:12px;color:#868e96;text-align:center">
    이 메일은 배당 공시 모니터링 시스템의 기준일 리마인드입니다.
  </div>
</div>"""


def build_etf_html_body(etf_name: str, stock_code: str, report_nm: str, date_str: str, acptno: str) -> str:
    """KIND ETF 분배 공시 알림 본문(청록 테마)."""
    kind_url = f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={acptno}"
    th = ("text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;"
          "font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px")
    td = ("padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef")
    return f"""\
<div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);overflow:hidden">
  <div style="background:linear-gradient(135deg,#006064,#00838f);color:#fff;padding:24px 32px">
    <h1 style="margin:0;font-size:20px;font-weight:600">📢 {report_nm}</h1>
    <div style="display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:20px;font-size:12px;margin-top:8px">ETF 분배 공시 알림</div>
  </div>
  <div style="padding:32px">
    <p style="color:#495057;font-size:15px">감시 대상 ETF에서 새로운 분배 관련 공시가 접수되었습니다.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr><th style="{th}">종목명</th><td style="{td}"><strong>{etf_name}</strong></td></tr>
      <tr><th style="{th}">종목코드</th><td style="{td}">{stock_code}</td></tr>
      <tr><th style="{th}">보고서명</th><td style="{td}">{report_nm}</td></tr>
      <tr><th style="{th}">공시시간</th><td style="{td}">{date_str}</td></tr>
    </table>
    <a href="{kind_url}" style="display:inline-block;background:#006064;color:#fff!important;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;margin-top:16px">📄 KIND에서 공시 원문 보기</a>
  </div>
  <div style="padding:16px 32px;background:#f8f9fa;font-size:12px;color:#868e96;text-align:center">
    이 메일은 배당·분배 공시 모니터링 시스템에서 자동 발송되었습니다.
  </div>
</div>"""


def _fmt_date(date: str) -> str:
    return f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date


def _fmt_won(v: str) -> str:
    """숫자 문자열이면 '원' 붙임. 그 외 그대로."""
    return f"{v}원" if v.replace(",", "").isdigit() else v


def build_html_body(d: Disclosure, extra: dict | None = None) -> str:
    """dart-mail-sender 와 동일 톤의 HTML 카드 본문.

    extra: dart_doc.fetch_detail() 결과(1주당 배당금·기준일·사유 등). 있으면 표에 추가.
    """
    formatted_date = _fmt_date(d.rcept_dt)
    rm = d.rm.strip() if d.rm and d.rm.strip() else "-"
    corp_name = d.corp_name.strip()
    report_nm = d.report_nm.strip()
    flr_nm = d.flr_nm.strip() if d.flr_nm and d.flr_nm.strip() else "-"
    th = ("text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;"
          "font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px")
    td = ("padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef")

    # 원문 상세 필드 → 강조 행 (금액 관련은 굵게)
    extra_rows = ""
    _WON = {"1주당 배당금", "배당금총액"}
    for label, val in (extra or {}).items():
        shown = _fmt_won(val) if label in _WON else (f"{val}%" if label == "시가배당률" else val)
        weight = "font-weight:700;color:#1a237e" if label in _WON else ""
        extra_rows += f'<tr><th style="{th}">{label}</th><td style="{td};{weight}">{shown}</td></tr>'
    return f"""\
<div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);overflow:hidden">
  <div style="background:linear-gradient(135deg,#1a237e,#283593);color:#fff;padding:24px 32px">
    <h1 style="margin:0;font-size:20px;font-weight:600">📢 {report_nm}</h1>
    <div style="display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:20px;font-size:12px;margin-top:8px">배당·분배 공시 알림</div>
  </div>
  <div style="padding:32px">
    <p style="color:#495057;font-size:15px">감시 대상 종목에서 새로운 배당·분배 관련 공시가 접수되었습니다.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr><th style="{th}">기업명</th><td style="{td}"><strong>{corp_name}</strong></td></tr>
      <tr><th style="{th}">종목코드</th><td style="{td}">{d.stock_code}</td></tr>
      <tr><th style="{th}">보고서명</th><td style="{td}">{report_nm}</td></tr>
      {extra_rows}
      <tr><th style="{th}">접수일자</th><td style="{td}">{formatted_date}</td></tr>
      <tr><th style="{th}">제출인</th><td style="{td}">{flr_nm}</td></tr>
      <tr><th style="{th}">비고</th><td style="{td}">{rm}</td></tr>
    </table>
    <a href="{d.dart_url}" style="display:inline-block;background:#1a237e;color:#fff!important;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;margin-top:16px">📄 DART에서 공시 원문 보기</a>
  </div>
  <div style="padding:16px 32px;background:#f8f9fa;font-size:12px;color:#868e96;text-align:center">
    이 메일은 배당 공시 모니터링 시스템에서 자동 발송되었습니다.
  </div>
</div>"""
