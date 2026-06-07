# -*- coding: utf-8 -*-
"""
주간회의자료(주식 시황회의) 자동 생성기.

대시보드 데이터(benchmarks.js / daily-data.js / portfolio-data) + 시장 센티먼트
(CNN Fear&Greed, AAII Bull/Bear)를 모아 공공기관 양식의 .xlsx 로 작성한다.

구성:
  □ 주간 주식시장 변동   — 한/미/유럽/일/중/MSCI × YTD/MTD/1W (benchmarks.js, 자동)
  □ 시장 센티먼트(신규)  — CNN F&G(지수+구성요소), AAII Bull/Bear, VIX (자동)
  □ 주요 Factor 점검     — 스마트 템플릿(뉴스 헤드라인 자동 시드 + 분석가 작성란)
  □ 주식 손익            — 평가손익(미실현)/매각이익(실현)/계 (portfolio-data, 자동)
  □ 국가 및 섹터 비중    — region/sector_exposure 룩스루 (portfolio-data, 자동)

손익/비중 계산은 portfolio.html 의 ytdMetrics / sector_exposure 룩스루 로직을 그대로 이식.

사용법:
  python weekly/weekly_report.py [--date YYYY-MM-DD] [--out PATH] [--no-sentiment]
    --date  대상(회의) 날짜. 생략 시 다가오는 월요일(오늘이 월요일이면 오늘).
    --out   출력 xlsx 경로. 생략 시 OneDrive 주간 발표자료 폴더.
"""
import sys, os, re, io, json, argparse, subprocess
from datetime import datetime, date, timedelta

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ONEDRIVE_BASE = os.path.join(os.path.expanduser("~"), "OneDrive", "삼성화재 주간 발표자료")

# ───────────────────────── 데이터 로드 ─────────────────────────
def _parse_assign(path, var_re):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(var_re, text, re.S)
    if not m:
        raise ValueError("assignment not found in " + path)
    return json.loads(m.group(1))


def load_benchmarks():
    return _parse_assign(os.path.join(REPO, "benchmarks.js"),
                         r"window\.BENCHMARKS\s*=\s*(\{.*\})\s*;?\s*$")


def load_daily():
    try:
        return _parse_assign(os.path.join(REPO, "daily-data.js"),
                             r"window\.DAILY\s*=\s*(\{.*\})\s*;?\s*$")
    except Exception:
        return None


def load_portfolio():
    """평문이 있으면 사용, 없으면 encrypt_data.py decrypt 로 생성."""
    plain = os.path.join(REPO, "portfolio-data.plain.js")
    if not os.path.exists(plain):
        subprocess.run([sys.executable, "encrypt_data.py", "decrypt"],
                       cwd=REPO, capture_output=True)
    with open(plain, "r", encoding="utf-8") as f:
        txt = f.read()
    m = re.search(r"PORTFOLIO_DATA\s*=\s*(\{.*?\})\s*;?\s*\n\s*(?:window\.|var |const |COUNTRY_NAMES)",
                  txt, re.S)
    if not m:
        m = re.search(r"PORTFOLIO_DATA\s*=\s*(\{.*\})\s*;?\s*$", txt, re.S)
    return json.loads(m.group(1))


def get_sentiment():
    try:
        sys.path.insert(0, HERE)
        import fetch_sentiment
        return fetch_sentiment.collect()
    except Exception as e:
        sys.stderr.write("sentiment fail: %s\n" % e)
        return {"cnn_fng": None, "aaii": None}


# ───────────────────────── 시장 변동 표 ─────────────────────────
# (라벨, ticker). 유럽=STOXX600, 일본=Nikkei, 중국=상해종합.
MARKET_MAP = [
    ("KOSPI", "^KS11"), ("KOSDAQ", "^KQ11"),
    ("S&P500", "^GSPC"), ("나스닥", "^IXIC"),
    ("유럽(STOXX600)", "^STOXX"), ("일본(니케이)", "^N225"),
    ("중국(상해종합)", "000001.SS"),
    ("ACWI", "ACWI"), ("EM", "EEM"),
]


def _ret_1w(idx, as_of):
    """history 에서 약 7 캘린더일 전 종가 대비 1주 수익률(소수)."""
    h = idx.get("history") or {}
    dates, vals = h.get("dates") or [], h.get("values") or []
    if len(dates) < 2:
        return None
    try:
        cur_d = datetime.strptime(as_of, "%Y-%m-%d").date()
    except Exception:
        cur_d = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    target = cur_d - timedelta(days=7)
    base = None
    for d, v in zip(dates, vals):
        try:
            dd = datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            continue
        if dd <= target:
            base = v
    cur = idx.get("current") or (vals[-1] if vals else None)
    if base and cur and base != 0:
        return cur / base - 1.0
    return None


def build_market_rows(bench):
    by_ticker = {x.get("ticker"): x for x in (bench.get("indices") or [])}
    as_of = bench.get("as_of")
    rows = []
    for label, tk in MARKET_MAP:
        x = by_ticker.get(tk)
        if not x:
            rows.append({"label": label, "ytd": None, "mtd": None, "w1": None,
                         "cur": None, "base": None})
            continue
        rows.append({
            "label": label,
            "ytd": _pct(x.get("ytd_pct")),
            "mtd": _pct(x.get("mtd_pct")),
            "w1": _ret_1w(x, as_of),
            "cur": x.get("current"),
            "base": x.get("baseline"),  # 연말 기준값
        })
    return rows, as_of


def _pct(v):
    """percent(예: 9.11) → 소수(0.0911). None 안전."""
    try:
        return float(v) / 100.0
    except (TypeError, ValueError):
        return None


# ───────────────────── 포트폴리오 손익/비중 ─────────────────────
SECTOR_KO = {
    "IT": "IT", "Financials": "금융", "Healthcare": "헬스케어",
    "Industrials": "산업재", "Cons Disc": "경기소비", "Communication": "커뮤니케이션",
    "Cons Staples": "필수소비", "Energy": "에너지", "Materials": "소재",
    "Utilities": "유틸리티", "Real Estate": "부동산",
}
REGION_BUCKET = {"한국": "한국", "미국": "미국", "유럽": "유럽",
                 "이머징": "이머징", "글로벌": "기타"}


def ytd_metrics(h):
    """portfolio.html ytdMetrics 이식. 반환 realized/unrealized/pnl."""
    start = h.get("start_2026")
    if start is None:
        start = h.get("book") or 0
    buy = h.get("ytd_buy") or 0
    sell = h.get("ytd_sell") or 0
    mkt = h.get("mkt") or 0
    cost = start + buy
    book_basis = h.get("book_basis")
    if book_basis is not None:
        cost_rem = book_basis
        cost_sold = cost - cost_rem
    elif sell > 0 and (mkt + sell) > 0:
        cost_sold = cost * sell / (mkt + sell)
        cost_rem = cost - cost_sold
    else:
        cost_sold = 0
        cost_rem = cost
    realized = sell - cost_sold
    unrealized = mkt - cost_rem
    return {"realized": realized, "unrealized": unrealized,
            "pnl": realized + unrealized}


def snapshot_holdings(pdata, cutoff):
    """historical.holdings_mkt 시리즈로 cutoff(YYYY-MM-DD) 시점 보유를 재구성.
    portfolio.html 스냅샷 재계산 로직 이식 → 각 holding 의 ytdMetrics 입력 dict 반환."""
    hist = pdata.get("historical") or {}
    hm = hist.get("holdings_mkt") or {}
    dates = hist.get("dates") or []
    if not dates:
        return None
    # cutoff 이하 마지막 인덱스
    idx = None
    for i, d in enumerate(dates):
        if d <= cutoff:
            idx = i
    if idx is None:
        return None
    trades = pdata.get("trades") or []
    out = []
    for h in pdata.get("holdings") or []:
        name = h.get("name")
        ser = hm.get(name)
        mkt_at = ser[idx] if (ser and idx < len(ser)) else (h.get("mkt") or 0)
        isin = h.get("isin") or ""
        buy = sell = 0.0
        for t in trades:
            if not isin or t.get("isin") != isin:
                continue
            if (t.get("date") or "") > cutoff:
                continue
            if t.get("action") == "매입":
                buy += t.get("amount") or 0
            elif t.get("action") == "매도":
                sell += t.get("amount") or 0
        start = h.get("start_2026")
        if start is None:
            start = h.get("book") or 0
        full_sell = h.get("ytd_sell") or 0
        full_cost_sold = h.get("cost_sold") or 0
        cost_sold_at = full_cost_sold * (sell / full_sell) if (full_sell > 0 and sell > 0) else 0
        book_basis_at = (start + buy) - cost_sold_at
        out.append({"region": h.get("region"), "mkt": mkt_at,
                    "start_2026": start, "ytd_buy": buy, "ytd_sell": sell,
                    "cost_sold": cost_sold_at, "book_basis": book_basis_at,
                    "sector_exposure": h.get("sector_exposure")})
    return out


def agg_pnl(holdings):
    r = u = 0.0
    for h in holdings:
        m = ytd_metrics(h)
        r += m["realized"]
        u += m["unrealized"]
    return {"realized": r, "unrealized": u, "pnl": r + u}


def build_pnl(pdata):
    """YTD 누계 + 6월(MTD) 분해. 6월 = 누계 − 5월말 스냅샷."""
    holdings = pdata.get("holdings") or []
    ytd = agg_pnl(holdings)
    may = None
    snap = snapshot_holdings(pdata, "2026-05-31")
    if snap:
        may = agg_pnl(snap)
    if may:
        jun = {"realized": ytd["realized"] - may["realized"],
               "unrealized": ytd["unrealized"] - may["unrealized"],
               "pnl": ytd["pnl"] - may["pnl"]}
    else:
        jun = None
    return {"ytd": ytd, "to_may": may, "jun": jun}


def build_weights(pdata):
    holdings = pdata.get("holdings") or []
    total = sum(h.get("mkt") or 0 for h in holdings)
    # 국가(지역) 비중 — region 기준
    country = {}
    for h in holdings:
        b = REGION_BUCKET.get(h.get("region"), "기타")
        country[b] = country.get(b, 0) + (h.get("mkt") or 0)
    country = {k: v / total for k, v in country.items()} if total else {}
    # 섹터 비중 — sector_exposure 룩스루
    sec = {}
    for h in holdings:
        mkt = h.get("mkt") or 0
        if mkt <= 0:
            continue
        exp = h.get("sector_exposure") or {}
        for s, e in exp.items():
            sec[s] = sec.get(s, 0) + (mkt / total) * e if total else 0
    country_order = ["한국", "미국", "유럽", "이머징", "기타"]
    country_rows = [(k, country.get(k, 0)) for k in country_order if k in country]
    sec_rows = sorted(((SECTOR_KO.get(s, s), v) for s, v in sec.items()),
                      key=lambda kv: kv[1], reverse=True)
    return country_rows, sec_rows


# ─────────────────── Factor 스마트 템플릿 시드 ───────────────────
_CLICKBAIT = re.compile(r"\$[0-9,]+|Became|Should You|Why You|Zacks|Motley|"
                        r"in \d+ Years|Best Stock|Buy Now|Rank", re.I)


def seed_events(daily):
    """daily-data.js 의 각 지역 commentary.events 에서 헤드라인 후보 수집.
    스코프 region/global 우선, 클릭베이트성 제목 제외, 중복 제거."""
    if not daily:
        return []
    seen, scored = set(), []
    for r in (daily.get("regions") or []):
        comm = r.get("commentary") or {}
        for e in (comm.get("events") or []):
            t = (e.get("title") or "").strip()
            if not t or t in seen or _CLICKBAIT.search(t):
                continue
            seen.add(t)
            scope = e.get("scope") or ""
            rank = 0 if scope in ("region", "global") else 1
            scored.append((rank, t))
    scored.sort(key=lambda x: x[0])
    return [t for _, t in scored][:8]


# ───────────────────────── XLSX 작성 ─────────────────────────
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="D9E1F2")
SEC_FILL = PatternFill("solid", fgColor="1F4E78")
SENT_FILL = PatternFill("solid", fgColor="FFF2CC")
F_NAME = "맑은 고딕"


def _cell(ws, coord, value, *, bold=False, size=10, align="left", fill=None,
          color=None, fmt=None, border=True, wrap=False):
    c = ws[coord]
    c.value = value
    c.font = Font(name=F_NAME, size=size, bold=bold,
                  color=color or ("FFFFFF" if fill is SEC_FILL else "000000"))
    c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    if fill:
        c.fill = fill
    if border:
        c.border = BORDER
    if fmt:
        c.number_format = fmt
    return c


def section_header(ws, row, text):
    c = _cell(ws, "A%d" % row, "□ " + text, bold=True, size=12, fill=SEC_FILL,
              color="FFFFFF", border=False)
    return row + 1


def build_xlsx(target_date, bench, pdata, daily, sentiment):
    wb = openpyxl.Workbook()
    ws = wb.active
    wk = (target_date.day - 1) // 7 + 1
    ws.title = target_date.strftime("%Y%m%d")
    ws.sheet_view.showGridLines = False
    for col, width in {"A": 16, "B": 13, "C": 11, "D": 11, "E": 11, "F": 11,
                       "G": 11, "H": 11, "I": 11}.items():
        ws.column_dimensions[col].width = width

    r = 1
    _cell(ws, "A1", "주식 시황회의 (%d월 %d주차)" % (target_date.month, wk),
          bold=True, size=15, border=False)
    ws.merge_cells("A1:I1")
    r = 3

    # ── □ 주간 주식시장 변동 ──
    r = section_header(ws, r, "주간 주식시장 변동")
    hdr_row = r
    for j, h in enumerate(["지수", "전일(현재)", "연말", "1W", "MTD", "YTD"]):
        _cell(ws, "%s%d" % (get_column_letter(1 + j), hdr_row), h,
              bold=True, align="center", fill=HEAD_FILL)
    r += 1
    market_rows, mkt_as_of = build_market_rows(bench)
    for mr in market_rows:
        _cell(ws, "A%d" % r, mr["label"], bold=True)
        _cell(ws, "B%d" % r, mr["cur"], align="right", fmt="#,##0.00")
        _cell(ws, "C%d" % r, mr["base"], align="right", fmt="#,##0.00")
        for col, key in (("D", "w1"), ("E", "mtd"), ("F", "ytd")):
            _cell(ws, "%s%d" % (col, r), mr[key], align="right", fmt="0.0%")
        r += 1
    _cell(ws, "A%d" % r, "기준일 %s" % (mkt_as_of or ""), size=9, border=False)
    r += 2

    # ── □ 시장 센티먼트 (신규) ──
    r = section_header(ws, r, "시장 센티먼트")
    cnn = (sentiment or {}).get("cnn_fng")
    aaii = (sentiment or {}).get("aaii")
    # CNN F&G
    if cnn and cnn.get("score") is not None:
        _cell(ws, "A%d" % r, "CNN Fear & Greed", bold=True, fill=SENT_FILL)
        _cell(ws, "B%d" % r, "%.0f (%s)" % (cnn["score"], _rate_ko(cnn.get("rating"))),
              align="center", fill=SENT_FILL, bold=True)
        _cell(ws, "C%d" % r, "1주전 %s" % _fmtnum(cnn.get("prev_1week")), align="center")
        _cell(ws, "D%d" % r, "1개월전 %s" % _fmtnum(cnn.get("prev_1month")), align="center")
        _cell(ws, "E%d" % r, "1년전 %s" % _fmtnum(cnn.get("prev_1year")), align="center")
        r += 1
        comps = cnn.get("components") or []
        for i in range(0, len(comps), 2):
            pair = comps[i:i + 2]
            txt = "  ·  ".join("%s %.0f(%s)" % (c["label"], c["score"], _rate_ko(c["rating"]))
                               for c in pair)
            _cell(ws, "A%d" % r, "구성요소", size=9, align="right")
            _cell(ws, "B%d" % r, txt, size=9, align="left", wrap=True)
            ws.merge_cells("B%d:I%d" % (r, r))
            r += 1
    # AAII
    if aaii and aaii.get("bullish") is not None:
        _cell(ws, "A%d" % r, "AAII 투자심리", bold=True, fill=SENT_FILL)
        _cell(ws, "B%d" % r, "강세 %.0f%%" % aaii["bullish"], align="center", fill=SENT_FILL)
        _cell(ws, "C%d" % r, "중립 %.0f%%" % aaii["neutral"], align="center")
        _cell(ws, "D%d" % r, "약세 %.0f%%" % aaii["bearish"], align="center")
        spread = aaii.get("spread")
        _cell(ws, "E%d" % r, "Bull-Bear %+.0f%%p" % spread if spread is not None else "",
              align="center", bold=True)
        avg = aaii.get("bull_hist_avg")
        _cell(ws, "F%d" % r, "강세 역사평균 %.1f%%" % avg if avg else "", align="center", size=9)
        r += 1
        prev = aaii.get("prev")
        if prev:
            _cell(ws, "A%d" % r, "직전주(%s)" % prev.get("date"), size=9, align="right")
            _cell(ws, "B%d" % r,
                  "강세 %.0f%% / 중립 %.0f%% / 약세 %.0f%% (Spread %+.0f%%p)"
                  % (prev["bullish"], prev["neutral"], prev["bearish"], prev["spread"]),
                  size=9, align="left")
            ws.merge_cells("B%d:I%d" % (r, r))
            r += 1
    # VIX (benchmarks)
    vix = next((x for x in (bench.get("indices") or []) if x.get("ticker") == "^VIX"), None)
    if vix:
        _cell(ws, "A%d" % r, "VIX (변동성)", bold=True, fill=SENT_FILL)
        _cell(ws, "B%d" % r, "%.2f" % (vix.get("current") or 0), align="center", fill=SENT_FILL)
        _cell(ws, "C%d" % r, "일간 %+.1f%%" % (vix.get("daily_pct") or 0), align="center")
        _cell(ws, "D%d" % r, "MTD %+.1f%%" % (vix.get("mtd_pct") or 0), align="center")
        r += 1
    r += 1

    # ── □ 주요 Factor 점검 (스마트 템플릿) ──
    r = section_header(ws, r, "주요 Factor 점검  (정량 자동 · 코멘트 직접 작성)")
    events = seed_events(daily)
    factors = [
        ("기업이익", ["(자동 시드 없음) 전세계/국내 EPS 변화율·컨센서스 상향 국가 기재", ""]),
        ("경제지표", ["주요 발표(고용·CPI·금리결정) 결과/컨센서스 기재", ""]),
        ("수급", ["국내(외국인·기관·예탁금)·해외(헤지펀드) 수급 동향 기재", ""]),
        ("주요 이벤트", (["[뉴스 시드] " + e for e in events] if events else
                       ["주요 일정/이벤트 기재", ""])),
        ("주요 보고서", ["증권사/리서치 코멘트 요약 기재", ""]),
    ]
    _cell(ws, "A%d" % r, "Factor", bold=True, align="center", fill=HEAD_FILL)
    _cell(ws, "B%d" % r, "내용", bold=True, align="center", fill=HEAD_FILL)
    ws.merge_cells("B%d:I%d" % (r, r))
    r += 1
    for name, lines in factors:
        start_r = r
        for k, ln in enumerate(lines):
            _cell(ws, "A%d" % r, name if k == 0 else "", bold=True, wrap=True)
            txt = (" - " + ln) if (ln and not ln.startswith("[")) else (ln or "")
            _cell(ws, "B%d" % r, txt, align="left", wrap=True, size=9)
            ws.merge_cells("B%d:I%d" % (r, r))
            r += 1
        if r - 1 > start_r:
            ws.merge_cells("A%d:A%d" % (start_r, r - 1))
    r += 1

    # ── □ 주식 손익 ──
    r = section_header(ws, r, "주식 손익  (단위: %s)" % (pdata.get("currency_unit") or "억원"))
    pnl = build_pnl(pdata)
    _cell(ws, "A%d" % r, "구분", bold=True, align="center", fill=HEAD_FILL)
    _cell(ws, "B%d" % r, "1~5월", bold=True, align="center", fill=HEAD_FILL)
    _cell(ws, "C%d" % r, "6월", bold=True, align="center", fill=HEAD_FILL)
    _cell(ws, "D%d" % r, "계(YTD)", bold=True, align="center", fill=HEAD_FILL)
    r += 1
    def pnl_row(label, key):
        nonlocal r
        _cell(ws, "A%d" % r, label, bold=True)
        may = pnl["to_may"][key] if pnl["to_may"] else None
        jun = pnl["jun"][key] if pnl["jun"] else None
        ytd = pnl["ytd"][key]
        _cell(ws, "B%d" % r, round(may, 1) if may is not None else "", align="right", fmt="#,##0.0")
        _cell(ws, "C%d" % r, round(jun, 1) if jun is not None else "", align="right", fmt="#,##0.0")
        _cell(ws, "D%d" % r, round(ytd, 1), align="right", fmt="#,##0.0", bold=True)
        r += 1
    pnl_row("평가손익 (미실현)", "unrealized")
    pnl_row("매각이익 (실현)", "realized")
    pnl_row("계", "pnl")
    r += 1

    # ── □ 국가 및 섹터 비중 ──
    r = section_header(ws, r, "국가 및 섹터 비중")
    country_rows, sec_rows = build_weights(pdata)
    _cell(ws, "A%d" % r, "국가", bold=True, align="center", fill=HEAD_FILL)
    _cell(ws, "B%d" % r, "비중", bold=True, align="center", fill=HEAD_FILL)
    _cell(ws, "D%d" % r, "섹터", bold=True, align="center", fill=HEAD_FILL)
    _cell(ws, "E%d" % r, "비중", bold=True, align="center", fill=HEAD_FILL)
    r += 1
    maxn = max(len(country_rows), len(sec_rows))
    for i in range(maxn):
        if i < len(country_rows):
            _cell(ws, "A%d" % r, country_rows[i][0], bold=True)
            _cell(ws, "B%d" % r, country_rows[i][1], align="right", fmt="0.0%")
        else:
            _cell(ws, "A%d" % r, "", border=True)
            _cell(ws, "B%d" % r, "", border=True)
        if i < len(sec_rows):
            _cell(ws, "D%d" % r, sec_rows[i][0], bold=True)
            _cell(ws, "E%d" % r, sec_rows[i][1], align="right", fmt="0.0%")
        else:
            _cell(ws, "D%d" % r, "", border=True)
            _cell(ws, "E%d" % r, "", border=True)
        r += 1
    return wb


def _rate_ko(rating):
    return {"extreme fear": "극단적 공포", "fear": "공포", "neutral": "중립",
            "greed": "탐욕", "extreme greed": "극단적 탐욕"}.get(
                (rating or "").lower(), rating or "")


def _fmtnum(v):
    return ("%.0f" % v) if isinstance(v, (int, float)) else "-"


# ───────────────────────── main ─────────────────────────
def next_monday(today):
    if today.weekday() == 0:
        return today
    return today + timedelta(days=(7 - today.weekday()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="대상 회의 날짜 YYYY-MM-DD")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-sentiment", action="store_true")
    ap.add_argument("--today", default=None, help="기준 오늘(테스트용) YYYY-MM-DD")
    args = ap.parse_args()

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    target = (datetime.strptime(args.date, "%Y-%m-%d").date() if args.date
              else next_monday(today))

    bench = load_benchmarks()
    daily = load_daily()
    pdata = load_portfolio()
    sentiment = {"cnn_fng": None, "aaii": None} if args.no_sentiment else get_sentiment()

    wb = build_xlsx(target, bench, pdata, daily, sentiment)

    out = args.out
    if not out:
        folder = os.path.join(ONEDRIVE_BASE, target.strftime("%Y%m%d"))
        os.makedirs(folder, exist_ok=True)
        out = os.path.join(folder, "주간회의자료_auto.xlsx")
    try:
        wb.save(out)
    except PermissionError:
        base, ext = os.path.splitext(out)
        out = base + "_" + datetime.now().strftime("%H%M%S") + ext
        wb.save(out)
    print("saved:", out)
    print("  market rows:", len(MARKET_MAP),
          "| sentiment:", "on" if not args.no_sentiment else "off",
          "| cnn:", bool(sentiment.get("cnn_fng")), "| aaii:", bool(sentiment.get("aaii")))


if __name__ == "__main__":
    main()
