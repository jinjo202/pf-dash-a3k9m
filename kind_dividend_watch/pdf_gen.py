"""배당공시 요약 PDF 생성 (fpdf2 + 한글폰트). 브라우저 불필요 → 러너에서 동작.

DART 원문(document.xml)에서 추출한 배당 상세를 1장짜리 PDF로 만든다.
한글 폰트: KOR_FONT_PATH env → Windows malgun → Linux nanum/noto 순.
실패 시 None(첨부 없이 메일은 발송).
"""

import io
import os
import tempfile

from dart_client import Disclosure

_FONT_CANDIDATES = [
    os.environ.get("KOR_FONT_PATH"),
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf",
]


def _font_path() -> str | None:
    for p in _FONT_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def make_dividend_pdf(d: Disclosure, extra: dict) -> str | None:
    """배당공시 요약 PDF를 임시파일로 생성하고 경로 반환. 실패 시 None."""
    font = _font_path()
    if not font:
        print("   ⚠️ 한글폰트 없음 — PDF 생략(KOR_FONT_PATH 설정 필요)")
        return None
    try:
        from fpdf import FPDF
    except ImportError:
        print("   ⚠️ fpdf2 미설치 — PDF 생략")
        return None

    corp = d.corp_name.strip()
    report = d.report_nm.strip()
    rcept_dt = f"{d.rcept_dt[:4]}-{d.rcept_dt[4:6]}-{d.rcept_dt[6:8]}" if len(d.rcept_dt) == 8 else d.rcept_dt

    rows = [
        ("기업명", corp),
        ("종목코드", d.stock_code),
        ("보고서명", report),
        ("접수일자", rcept_dt),
        ("제출인", d.flr_nm.strip() or "-"),
    ]
    # 배당 상세(추출된 것만)
    label_map = [
        ("배당구분", "배당구분"), ("1주당 배당금(원)", "1주당 배당금"),
        ("시가배당률(%)", "시가배당률"), ("배당금총액(원)", "배당금총액"),
        ("배당기준일", "배당기준일"), ("배당금지급 예정일", "지급예정일"),
        ("기준일", "기준일"), ("사유", "사유"),
    ]
    detail = [(lbl, extra[k]) for lbl, k in label_map if extra.get(k)]

    try:
        pdf = FPDF(format="A4")
        pdf.add_page()
        pdf.add_font("kor", "", font)
        pdf.set_font("kor", size=16)
        pdf.set_text_color(26, 35, 126)
        pdf.cell(0, 12, "현금ㆍ현물배당 결정 공시", new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(200, 200, 200)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(4)

        avail = pdf.w - pdf.l_margin - pdf.r_margin      # 190mm
        lbl_w, val_w = 45, avail - 45

        def table(title, items):
            if not items:
                return
            pdf.set_font("kor", size=11)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(avail, 8, title, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(20, 20, 20)
            for lbl, val in items:
                pdf.set_font("kor", size=10)
                pdf.set_fill_color(245, 246, 248)
                y0 = pdf.get_y()
                pdf.multi_cell(lbl_w, 9, f" {lbl}", border=1, fill=True,
                               new_x="RIGHT", new_y="TOP", max_line_height=9)
                pdf.set_xy(pdf.l_margin + lbl_w, y0)
                pdf.multi_cell(val_w, 9, f" {val}", border=1,
                               new_x="LMARGIN", new_y="NEXT", max_line_height=9)
            pdf.ln(3)

        table("공시 기본정보", rows)
        table("배당 상세", detail)

        pdf.set_font("kor", size=9)
        pdf.set_text_color(120, 120, 120)
        pdf.multi_cell(avail, 6, f"DART 원문: {d.dart_url}")
        pdf.multi_cell(avail, 6, "※ 본 PDF는 배당공시 모니터링 시스템이 DART 원문에서 자동 생성한 요약입니다.")

        out = os.path.join(tempfile.gettempdir(), f"배당공시_{corp}_{d.rcept_dt}.pdf".replace("/", "_"))
        pdf.output(out)
        return out
    except Exception as e:
        print(f"   ⚠️ PDF 생성 실패: {e}")
        return None
