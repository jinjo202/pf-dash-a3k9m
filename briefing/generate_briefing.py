# -*- coding: utf-8 -*-
"""
서버사이드(GitHub Actions) 한국어 시황 브리핑 생성기.

로컬 예약 작업(Claude Code)이 하던 브리핑 작성을 Claude API 로 옮긴 것.
PC 가 켜져 있는지와 무관하게 GitHub Actions 에서 매일 실행된다.

흐름:
  1. daily-data.js(window.DAILY) + benchmarks.js(window.BENCHMARKS) 파싱
  2. region(asia|us) 별로 관련 데이터만 추려 프롬프트 구성
  3. Claude API 로 {title, paragraphs, report} JSON 생성
  4. 아카이브 js + briefings/{as_of}.md (+ us: briefing-data.js) 갱신

사용법:
  python generate_briefing.py <asia|us> [--as-of YYYY-MM-DD] [--dry-run] [--skip-if-exists]

환경변수 (자격증명: 아래 중 하나 — 구독 우선):
  CLAUDE_CODE_OAUTH_TOKEN  구독(Max) 차감. Claude Code CLI(claude -p) 경유. 추가 과금 없음.
  ANTHROPIC_API_KEY        종량제 API 키 (구독 토큰 없을 때 폴백)
  ANTHROPIC_MODEL          (선택) 모델 alias. 기본 claude-sonnet-4-5

종료코드: 0 성공 / 2 인자·환경 문제 / 3 데이터 문제 / 4 API·파싱 실패
"""
import sys, os, re, json, argparse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DAILY_JS = os.path.join(REPO, "daily-data.js")
BENCH_JS = os.path.join(REPO, "benchmarks.js")
BRIEFINGS_DIR = os.path.join(REPO, "briefings")
ARCHIVE_ASIA = os.path.join(REPO, "briefings-archive-asia.js")
ARCHIVE_US = os.path.join(REPO, "briefings-archive.js")
BRIEFING_DATA_US = os.path.join(REPO, "briefing-data.js")
DRAFT_ASIA_JS = os.path.join(HERE, "_draft-asia.js")  # 초안 임시 출력(비커밋)

# ANTHROPIC_MODEL 가 비어 있거나 미설정이면 sonnet 기본(비용 절감).
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-5"
MAX_KEEP = 120


# ----------------------------------------------------------------------------
# 데이터 로드
# ----------------------------------------------------------------------------
def _parse_assign(path, var_re):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(var_re, text, re.S)
    if not m:
        raise ValueError("assignment not found in " + path)
    return json.loads(m.group(1))


def load_daily():
    return _parse_assign(DAILY_JS, r"window\.DAILY\s*=\s*(\{.*\})\s*;?\s*$")


def load_benchmarks():
    try:
        return _parse_assign(BENCH_JS, r"window\.BENCHMARKS\s*=\s*(\{.*\})\s*;?\s*$")
    except Exception:
        return None


def slim_region(r):
    """프롬프트용으로 region 에서 무거운 spark/history 제거하고 필요한 필드만."""
    def slim_indices(lst):
        out = []
        for x in (lst or []):
            out.append({k: x.get(k) for k in
                        ("ticker", "name", "price", "chg", "chgPct", "ytdPct", "mtdPct")
                        if x.get(k) is not None})
        return out

    def slim_movers(lst):
        out = []
        for x in (lst or []):
            out.append({k: x.get(k) for k in
                        ("name", "ticker", "chgPct", "reason", "detail")
                        if x.get(k) is not None})
        return out

    comm = r.get("commentary") or {}
    slim = {
        "key": r.get("key"),
        "name": r.get("name"),
        "as_of": r.get("as_of"),
        "prev_date": r.get("prev_date"),
        "indices": slim_indices(r.get("indices")),
        "sectors": [{"name": s.get("name"), "chgPct": s.get("chgPct")}
                    for s in (r.get("sectors") or [])],
        "commentary": {
            "movers": slim_movers(comm.get("movers")),
            "events": [{"title": e.get("title"), "source": e.get("source"),
                        "scope": e.get("scope")}
                       for e in (comm.get("events") or [])],
        },
    }
    if r.get("featured"):
        slim["featured"] = r.get("featured")
    return slim


def slim_benchmarks(bench, tickers):
    if not bench:
        return []
    want = set(tickers)
    out = []
    for x in (bench.get("indices") or []):
        # KR 10Y 등 ticker 가 "MANUAL" 인 항목은 name 으로도 매칭.
        if x.get("ticker") in want or x.get("name") in want:
            out.append({k: x.get(k) for k in
                        ("name", "ticker", "current", "daily_pct", "ytd_pct",
                         "prev_close", "decimals")
                        if x.get(k) is not None})
    return out


KR_EXPORTS = os.path.join(REPO, "weekly", "kr_exports.json")


def load_latest_export(as_of, max_age_days=3):
    """관세청 수출 통계 최신 release 를 반환하되, 발표 as_of 가 기준일에서
    max_age_days 이내(=갓 발표)인 경우에만. 그 외엔 None → 수출 문단 생략.
    (매일 브리핑에 오래된 수출 수치가 반복 노출되는 것을 막는다.)"""
    try:
        with open(KR_EXPORTS, "r", encoding="utf-8") as f:
            data = json.load(f)
        releases = data.get("releases") or []
        if not releases:
            return None
        rel = releases[0]
        rao = rel.get("as_of")
        if not rao:
            return None
        d0 = datetime.strptime(as_of, "%Y-%m-%d").date()
        d1 = datetime.strptime(rao, "%Y-%m-%d").date()
        if abs((d0 - d1).days) <= max_age_days:
            return rel
    except Exception:
        return None
    return None


# ----------------------------------------------------------------------------
# 연합인포맥스 뉴스 (시장 주도 이벤트 큐레이션 — 프롬프트 맥락용)
# ----------------------------------------------------------------------------
# 섹션 RSS(뉴스구독 CMS S1N{n}). asia/us 별로 시장 주도 뉴스 섹션만 선별.
EINFOMAX_RSS = "https://news.einfomax.co.kr/rss/S1N%d.xml"
EINFOMAX_SECTIONS = {
    "asia": [(2, "증권"), (16, "채권/외환"), (15, "정책/금융")],
    "us":   [(23, "국제"), (21, "해외주식"), (16, "채권/외환")],
}
# 시황과 무관한 노이즈 머리말([...]) — 헤드라인 앞부분에 오면 제외.
_EINFOMAX_NOISE = ("인사", "부고", "포토", "시사금융용어", "인물", "동정",
                   "사람들", "알림", "게시판", "신간", "채용", "특징주디",
                   "표", "표)", "코스피 마감", "코스닥 마감")


def _strip_tags(s):
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    import html as _h
    return _h.unescape(_h.unescape(s)).strip()  # 이중 인코딩(&amp;quot;) 대응


def _rss_items(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "replace")
    out = []
    for m in re.finditer(r"<item>(.*?)</item>", data, re.S):
        blk = m.group(1)
        tm = re.search(r"<title>(.*?)</title>", blk, re.S)
        dm = re.search(r"<description>(.*?)</description>", blk, re.S)
        title = _strip_tags(tm.group(1)) if tm else ""
        if not title:
            continue
        out.append({"title": title[:140],
                    "desc": (_strip_tags(dm.group(1)) if dm else "")[:180]})
        if len(out) >= limit:
            break
    return out


def _is_noise(title):
    m = re.match(r"^\s*\[([^\]]{1,12})\]", title or "")
    if m and any(k in m.group(1) for k in _EINFOMAX_NOISE):
        return True
    return False


def fetch_einfomax_news(region, per_section=7, cap=12):
    """region(asia|us) 별 인포맥스 섹션 RSS에서 시장 주도 헤드라인을 큐레이션.
    실패·네트워크 문제 시 빈 리스트(생성은 계속). 수치 근거로는 쓰지 않는다."""
    sections = EINFOMAX_SECTIONS.get(region) or []
    seen, out = set(), []
    for num, label in sections:
        try:
            items = _rss_items(EINFOMAX_RSS % num, per_section)
        except Exception:
            continue
        for it in items:
            t = it["title"]
            if _is_noise(t):
                continue
            key = re.sub(r"\s+", "", t)[:40]
            if key in seen:
                continue
            seen.add(key)
            out.append({"title": t, "desc": it["desc"], "section": label})
    return out[:cap]


# ----------------------------------------------------------------------------
# 장중 실시간 지수 (초안용 — 네이버 금융)
# ----------------------------------------------------------------------------
def _http_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0",
                      "Referer": "https://m.stock.naver.com/"})
    return json.loads(urllib.request.urlopen(url=req, timeout=10)
                      .read().decode("utf-8", "replace"))


# (country, index label, kind, naver symbol)
NAVER_DRAFT_IDX = [
    ("한국", "코스피", "domestic", "KOSPI"),
    ("한국", "코스닥", "domestic", "KOSDAQ"),
    ("일본", "닛케이", "world", ".N225"),
    ("중국", "상해종합", "world", ".SSEC"),
]


def fetch_intraday_indices():
    """네이버 실시간 지수(장중 잠정). 초안용. 실패 항목은 건너뜀."""
    out = []
    for country, label, kind, sym in NAVER_DRAFT_IDX:
        try:
            if kind == "domestic":
                d = _http_json("https://polling.finance.naver.com/api/realtime/"
                               "domestic/index/" + sym)
                it = (d.get("datas") or [None])[0]
            else:
                it = _http_json("https://api.stock.naver.com/index/" + sym + "/basic")
            if not it:
                continue
            ratio = it.get("fluctuationsRatioRaw", it.get("fluctuationsRatio"))
            out.append({
                "country": country, "index": label,
                "chgPct": float(str(ratio).replace(",", "")),
                "now": it.get("closePrice"),
                "status": it.get("marketStatus"),
            })
        except Exception:
            continue
    return out


def kst_today():
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")


# ----------------------------------------------------------------------------
# 작성 규칙 (SKILL.md 발췌)
# ----------------------------------------------------------------------------
RULES_ASIA = """당신은 매일 아시아 증시(한국·일본·중국·홍콩) 마감 후 한국어 시황 브리핑을 작성하는 증권사 애널리스트입니다.

[지수 매핑] 국가 대표지수: 한국=코스피(KOSPI, 코스닥은 보조), 일본=닛케이225, 중국=상해종합(SSE). 항셍(HSI, 홍콩)·선전성분은 본문 보조 서술에만.
benchmarks: KRW=X=원/달러 환율, "KR 10Y"=한국 국고채 10년 금리(payload 에 있을 때만).

[휴장 판정 — 매우 중요, 절대 추정 금지]
각 시장(korea·japan·china)의 휴장 여부는 오직 그 region 의 as_of 로만 판정한다.
- region 의 as_of 가 작성 기준일(as_of)과 **같으면 그 시장은 그날 정상 거래된 것**이다. 이 경우 "휴장"이라는 단어를 절대 쓰지 말 것.
- region 의 as_of 가 작성 기준일보다 **이전 날짜일 때만** 그 시장이 해당일 휴장(또는 데이터 미반영)이며, 이때는 "전 거래일(해당 as_of) 종가 기준"으로 서술한다.
- 데이터에 없는 휴장·공휴일·반차 등을 추측하거나 지어내지 말 것. 특히 한국 증시가 거래된 날(korea.as_of == 기준일)에 "한국 휴장"이라고 쓰는 것은 명백한 오류다.

[paragraphs 작성 — 아래 순서·형식을 정확히 따른다. 짧고 간결한 존댓말 문장, 어절 단위로 끊어 쓴다]
1. 첫 문단은 정확히 "금일 아시아 증시 시황 보고 드립니다.".
2. 총평(1~2문장): 한국·일본·중국의 방향과 각 한 줄 이유를 묶어 혼조/동반 여부까지. 예: "3분기 첫 거래일 한국은 연기금 매도 우려 속에 하락, 일본·중국은 기술주 강세에 상승하며 혼조세를 보였습니다.".
3. 지수 통계 라인 — 반드시 "* " 로 시작(렌더러가 자동 처리). 국가 대표지수 3개를 한 줄로 묶는다: "* {M.D}(연초대비): 한국 △X.X%({+/△}ytd), 일본 +X.X%({+/△}ytd), 중국 +X.X%({+/△}ytd)". 한국=코스피, 일본=닛케이225, 중국=상해종합. {M.D}=기준일 월.일(예 7.1). 앞 %는 chgPct, 괄호는 ytdPct(소수1자리). 하락 △, 상승 +.
4. 한국 문단: 코스피와 코스닥을 각각 등락률+주도 이유(sectors·movers 근거)로 서술. 두 지수 방향이 엇갈리면 대비해서. (예: 코스피는 외인·연기금 매도로 하락, 코스닥은 소부장·전력기기 강세로 상승.)
5. 수출 문단 — payload 에 [kr_exports] 가 있을 때만 작성(없으면 이 문단 자체를 생략). 관세청 통계를 서술: 총수출액(export_usd_bn)·전년대비(export_yoy), 반도체 수출액(semi_usd_bn)·전년대비(semi_yoy), note 의 맥락(역대 최대 등). 데이터에 있는 값만, 단위·증감률을 지어내지 말 것.
6. 반도체·주도주 문단: 삼성전자·SK하이닉스 등 대형주 등락을 문장 안에 괄호로 병기(예 "삼성전자(△5.8%)")하고, 매수세 분산·쏠림 완화 등 흐름을 movers·sectors 로 서술.
7. 일본·중국 문단(1~2문장): 주도 업종·연속 상승 여부 등 간결히.
8. 환율·금리 문단: 원/달러를 "전일대비 등락(원)"과 레벨로 서술(예 "+5원 상승(1,554원)", KRW=X 의 current 와 전일대비). "KR 10Y" 데이터가 payload 에 있으면 국고채 10년 금리도 레벨과 함께 한 문장(bp 변동은 prev_close 대비 (current-prev_close)*100 으로 계산, prev_close 없으면 레벨만). 없으면 금리는 생략.

[필수 규칙]
- 종목 등락률은 문장 안에 괄호로 병기(예 "삼성전자(△5.8%)"). 별도 "※ " 나열 라인은 만들지 않는다(위 3번 "* " 지수 라인만 예외).
- [연합인포맥스 주요 뉴스] 헤드라인이 제공되면 총평·한국·주도주 문단에서 '그날 시장을 움직인 핵심 이벤트'를 짚는 근거로 적극 활용한다(연기금·외인 수급, 정책, 반도체 단가 등). 단 정성적 맥락·방향·인용에만 쓰고, 헤드라인 속 구체 수치는 데이터로 확인되지 않으면 옮기지 말 것.
- 모든 수치는 데이터에 있는 실제 값만. 등락률·연초대비·수출·환율·금리를 절대 지어내지 말 것.
- 하락은 △, 상승은 +.
- movers 의 영문 detail/reason 은 한국어로 자연스럽게 풀어 해석(영어 그대로 붙여넣지 말 것).
- 데이터로 검증 불가한 인용·일정·통계(총재 발언, "외국인 N일 연속 순매도", "시총 N조 돌파" 등)는 절대 지어내지 말 것.
- 과장·단정·투자권유 금지. "안녕하십니까"/"감사합니다." 는 쓰지 않는다.
- 각 문단은 어절(공백) 단위로 자연스럽게 끊어 쓸 것. 단어 중간에서 줄이 나뉘지 않도록 한 문장이 지나치게 길어지지 않게 작성.

[title] "{N월 N일} 아시아 증시 시황" (as_of 기준)."""

RULES_US = """당신은 매일 미국장 마감 후 한국어 금융시황 브리핑을 작성하는 증권사 애널리스트입니다.

[미국 휴장 판정] us.as_of 가 europe.as_of 보다 이른 날짜이면 미국 휴장. 휴장이면 europe.as_of 기준으로 유럽 중심(+미국 휴장 안내 한 줄). 평상시면 us.as_of 기준 미국 중심+유럽 보조.
benchmarks ticker: ^VIX, ^TNX(미10년물), CL=F(WTI), KRW=X(원/달러), ^SOX(필라델피아 반도체).

[paragraphs 작성 — 8~12문단, 차분한 존댓말 서술체]
- 첫 문단은 정확히 "안녕하십니까"(마침표 없음). 마지막 문단은 "감사합니다.".
- 둘째 문단 "{M}월 {D}일 글로벌 증시 동향입니다."(미국 휴장이면 " 미국은 휴장이었습니다." 추가).
- 지수 통계 라인은 반드시 "* " 로 시작(S&P500·나스닥·다우·Euro Stoxx50 등 데이터에 있는 지수), 전일대비%와 (연초대비 ytdPct) 병기.
- 종목 등락률 병기 라인은 반드시 "※ " 로 시작.
- bold+underline 강조 문단은 맨 앞에 "_ "(언더스코어+공백)를 붙임. 헤드라인·주요 마감 수치·이번주 전망 등에 사용하되 한 브리핑에 3~5개 정도만.
- 매크로/정책/이벤트 1~2문단(events·movers 근거), 특징 종목 1~2문단, 채권·유가·환율 한 문단(^TNX/CL=F/KRW=X), 전망 문단.

[필수 규칙]
- [연합인포맥스 주요 뉴스] 헤드라인이 제공되면 매크로·정책·이벤트·특징종목 문단에서 '그날 시장을 움직인 핵심 이벤트'를 짚는 근거로 적극 활용한다(연준·금리, 빅테크, 반도체 등). 단 정성적 맥락·방향·인용에만 쓰고, 헤드라인 속 구체 수치는 데이터로 확인되지 않으면 옮기지 말 것.
- 모든 수치는 데이터에 있는 실제 값만. 데이터에 없는 구체 수치(목표주가 등)는 movers detail/reason 에 있을 때만 인용. 절대 지어내지 말 것.
- 하락은 △, 상승은 +. movers 영문은 한국어로 풀어 해석.
- 반도체가 크게 움직였으면 ^SOX 수치 활용.
- 과장·단정·투자권유 금지.
- 각 문단은 어절(공백) 단위로 자연스럽게 끊어 쓸 것. 단어 중간에서 줄이 나뉘지 않도록 한 문장이 지나치게 길어지지 않게 작성.

[title] "{N월 N일} 글로벌 증시 동향" (as_of 기준)."""

RULES_REPORT = """[report 구조 — 워드(.docx) 개조식 보고서용]
paragraphs 와 같은 데이터·사실에 기반하되 개조식(명사형 종결)으로 재구성.
형식: {"headline": "{N월 N일} ...", "sections": [{"head": "...", "points": [{"text": "...", "subs": ["...", ...]}]}]}
- sections 4~6개. 각 head 는 그날 핵심을 명사형으로 끝나는 한 문장(2줄 이하). head 만 읽어도 흐름 이해되게.
- 각 section.points 2~3개를 MECE 하게. 각 point.text 는 명사형 종결+숫자 근거 포함(한 줄, 35자 이내 권장).
- 부연이 필요한 point 에만 subs(없으면 생략). 보통 종목별 등락률 병기를 subs 로. subs 각 항목도 35자 이내 권장.
- head/points/subs 텍스트에 □/-/·/*/※ 기호를 직접 붙이지 말 것(렌더러가 자동).
- 검증 불가한 인용·수치는 절대 넣지 말 것.
- 텍스트는 어절(공백 단위) 경계에서만 자연스럽게 끊어지도록 간결하게 작성. 단어 중간에서 잘리지 않게 한 항목이 한 줄에 들어오는 것을 목표로 할 것."""

RULES_OUTLOOK = """[outlook — "오늘의 관전 포인트" (앞을 내다보는 진짜 전망)]
향후를 내다보는 관전 포인트 3~4개를 문자열 배열로 작성한다. 이것은 대시보드에서 '전망'으로 표시된다.
- 반드시 '앞으로'에 초점: 다가올 정규장·다음 거래일·이번주에 주목할 것. 예정된 발표·지표·이벤트(FOMC·CPI·고용·실적·수급 이벤트), 주목할 지수/종목 레벨·분기점, 잠재 촉매·리스크 요인.
- 오늘 이미 확정된 등락의 단순 재탕 금지(예: "삼성전자 △5.8% 하락", "코스피 △2% 마감"은 전망이 아니다). 그 사실이 '앞으로'에 주는 함의로 바꿔 쓸 것(예: "반도체 단가 반등 여부가 삼성전자 주가 방향 가늠자").
- [연합인포맥스 주요 뉴스]·events·featured 에서 향후 일정·촉매 단서를 적극 활용.
- 데이터·뉴스로 확인되지 않는 구체 일정·수치는 지어내지 말 것. 각 항목 45자 이내, 명사형 종결, 기호(□·-··) 붙이지 말 것."""

RULES_DRAFT_ASIA = """[초안 모드 — 장중 잠정치, 매우 중요]
지금은 아시아장 마감 전 '초안(preview)' 시점이다. 확정 종가가 아직 없다.
- 지수 등락은 아래 [장중 잠정 지수(네이버 실시간)]의 chgPct 를 사용한다(daily-data 의 값이 아니라 이것).
- 제목 끝에 반드시 " (초안)" 을 붙인다. 총평 첫 문장에서 '장중 잠정치 기준'임을 밝힌다.
- 3번 지수 통계 라인은 "* {M.D} 장중잠정: 한국 △X.X%, 코스닥 +X.X%, 일본 +X.X%, 중국 +X.X%" 형식(연초대비 괄호는 생략).
- 확정 마감치·개별 종목 확정 등락을 단정하지 말 것. 대신 [연합인포맥스 주요 뉴스]를 최대한 활용해 '오늘 시장을 움직인 이슈·수급·업종 방향'을 서술한다(예시자료 톤).
- 수출·국고채 등 확정 데이터가 없으면 해당 문단은 생략. 없는 수치를 지어내지 말 것.
- outlook(관전 포인트)은 마감·다음 세션에서 확인할 것 중심으로."""

OUTPUT_SPEC = """[출력 형식 — 매우 중요]
오직 하나의 JSON 객체만 출력한다(설명·마크다운 코드펜스 금지). 키:
  "title":      문자열
  "paragraphs": 문자열 배열(위 규칙의 prefix 컨벤션 "* "/"※ "/"_ " 정확히 준수)
  "report":     {"headline": 문자열, "sections": [...]}
  "outlook":    문자열 배열(3~4개, 앞을 내다보는 관전 포인트 — 오늘 등락 재탕 금지)
as_of/generated_utc 는 출력하지 말 것(스크립트가 채운다)."""


# ----------------------------------------------------------------------------
# Claude API 호출
# ----------------------------------------------------------------------------
# 유료(API) 청구 경로 차단용 env 목록 — CLI 경로에서 제거해 구독 OAuth만 남긴다(fail-closed).
_BILLING_ENV_STRIP = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_DEFAULT_HEADERS",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
    "AWS_BEARER_TOKEN_BEDROCK",
)


def call_claude(system_prompt, user_payload):
    """구독(CLAUDE_CODE_OAUTH_TOKEN) 우선 → 없으면 API 키(ANTHROPIC_API_KEY) 폴백."""
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return _call_claude_cli(system_prompt, user_payload)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _call_claude_sdk(system_prompt, user_payload)
    sys.stderr.write(
        "자격증명 없음: CLAUDE_CODE_OAUTH_TOKEN(구독) 또는 ANTHROPIC_API_KEY(종량제) 필요\n"
    )
    sys.exit(2)


def _call_claude_cli(system_prompt, user_payload):
    """Claude Code CLI(claude -p)로 구독에서 차감. API 청구 경로는 env에서 제거(fail-closed)."""
    import shutil, subprocess
    claude_bin = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"
    # prefill을 못 쓰므로 시스템 프롬프트로 JSON 단독 출력을 강제한다.
    sys_full = system_prompt + (
        "\n\n[출력 형식] 유효한 JSON 객체 하나만 출력한다. "
        "코드펜스(```), 설명, 머리말 없이 '{' 로 시작해 '}' 로 끝나야 한다."
    )
    env = {k: v for k, v in os.environ.items() if k not in _BILLING_ENV_STRIP}
    cmd = [
        claude_bin, "-p",
        "--append-system-prompt", sys_full,
        "--model", DEFAULT_MODEL,
        "--output-format", "json",
    ]
    try:
        proc = subprocess.run(
            cmd, input=user_payload, capture_output=True,
            text=True, encoding="utf-8", timeout=600, env=env,
        )
    except FileNotFoundError:
        sys.stderr.write("claude CLI 없음. 설치: npm i -g @anthropic-ai/claude-code\n")
        sys.exit(2)
    if proc.returncode != 0:
        sys.stderr.write(f"claude -p 실패 ({proc.returncode}): {(proc.stderr or '')[:600]}\n")
        sys.exit(2)
    # --output-format json → {"type":"result","result":"<text>", ...}
    text = proc.stdout
    try:
        env_out = json.loads(proc.stdout)
        if isinstance(env_out, dict) and isinstance(env_out.get("result"), str):
            text = env_out["result"]
    except Exception:
        pass
    return _parse_json_loose(text)


def _call_claude_sdk(system_prompt, user_payload):
    try:
        from anthropic import Anthropic
    except ImportError:
        sys.stderr.write("anthropic SDK not installed. pip install anthropic\n")
        sys.exit(2)
    client = Anthropic()
    msg = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_payload},
            # 어시스턴트 턴을 "{" 로 prefill → JSON 객체만 이어 쓰게 강제.
            {"role": "assistant", "content": "{"},
        ],
    )
    text = "".join(getattr(b, "text", "") for b in msg.content)
    raw = "{" + text
    return _parse_json_loose(raw)


def _parse_json_loose(raw):
    raw = raw.strip()
    # 혹시 코드펜스가 섞여 오면 제거
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    # 첫 { 부터 마지막 } 까지
    s = raw.find("{")
    e = raw.rfind("}")
    if s >= 0 and e > s:
        raw = raw[s:e + 1]
    return json.loads(raw)


# ----------------------------------------------------------------------------
# as_of 결정 + 프롬프트 구성
# ----------------------------------------------------------------------------
def regions_by_key(daily):
    return {r.get("key"): r for r in (daily.get("regions") or [])}


def build_request(region, daily, bench, override_as_of=None, draft=False):
    rk = regions_by_key(daily)
    exports_payload = None
    intraday = None
    if region == "asia":
        korea = rk.get("korea") or {}
        if draft:
            # 초안: 마감 전이므로 오늘(KST) 기준 + 네이버 장중 실시간 지수.
            as_of = override_as_of or kst_today()
            intraday = fetch_intraday_indices()
        else:
            as_of = override_as_of or korea.get("as_of") or daily.get("as_of")
        regions_payload = [slim_region(rk[k]) for k in ("korea", "japan", "china")
                           if k in rk]
        bench_payload = slim_benchmarks(bench, ["KRW=X", "KR 10Y"])
        if as_of and not draft:
            exports_payload = load_latest_export(as_of)
        rules = RULES_ASIA
    else:
        us = rk.get("us") or {}
        eu = rk.get("europe") or {}
        us_ao = us.get("as_of") or ""
        eu_ao = eu.get("as_of") or ""
        us_closed = bool(us_ao and eu_ao and us_ao < eu_ao)
        as_of = override_as_of or (eu_ao if us_closed else us_ao) or daily.get("as_of")
        regions_payload = [slim_region(rk[k]) for k in ("us", "europe") if k in rk]
        bench_payload = slim_benchmarks(bench, ["^VIX", "^TNX", "CL=F", "KRW=X", "^SOX"])
        rules = RULES_US

    parts = [rules, RULES_REPORT, RULES_OUTLOOK]
    if draft and region == "asia":
        parts.insert(1, RULES_DRAFT_ASIA)
    parts.append(OUTPUT_SPEC)
    system_prompt = "\n\n".join(parts)
    d = datetime.strptime(as_of, "%Y-%m-%d")
    intraday_block = ""
    if intraday:
        intraday_block = ("[장중 잠정 지수 (네이버 실시간, 확정 아님 — 초안 지수 라인에 사용)]\n%s\n\n"
                          % json.dumps(intraday, ensure_ascii=False))
    exports_block = ""
    if exports_payload:
        exports_block = ("[kr_exports 관세청 수출통계 (갓 발표)]\n%s\n\n"
                         % json.dumps(exports_payload, ensure_ascii=False))
    news_block = ""
    einfo = fetch_einfomax_news(region)
    if einfo:
        news_block = (
            "[연합인포맥스 주요 뉴스 헤드라인 — 시장 주도 이벤트 파악·정성적 인용에만 사용, "
            "구체 수치는 반드시 위 데이터에서만]\n%s\n\n"
            % json.dumps(einfo, ensure_ascii=False))
    user_payload = (
        "작성 기준일(as_of): %s (= %d월 %d일)\n\n"
        "[daily-data.js regions]\n%s\n\n"
        "[benchmarks.js indices]\n%s\n\n"
        "%s%s%s"
        "위 데이터만 근거로 규칙에 따라 JSON 을 출력하라."
        % (as_of, d.month, d.day,
           json.dumps(regions_payload, ensure_ascii=False),
           json.dumps(bench_payload, ensure_ascii=False),
           intraday_block, exports_block, news_block)
    )
    return as_of, system_prompt, user_payload


# ----------------------------------------------------------------------------
# 게시 파일 작성
# ----------------------------------------------------------------------------
def load_archive(path, var):
    if not os.path.exists(path):
        return []
    try:
        return _parse_assign(path, var + r"\s*=\s*(\[.*\])\s*;?\s*$")
    except Exception:
        return []


def write_archive(path, var, header, arr):
    body = json.dumps(arr, ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header.rstrip() + "\n" + var + " = " + body + ";\n")


def upsert(arr, today):
    as_of = today["as_of"]
    arr = [b for b in arr if b.get("as_of") != as_of]
    arr.insert(0, today)
    arr.sort(key=lambda b: b.get("as_of") or "", reverse=True)
    return arr[:MAX_KEEP]


def publish(region, today):
    os.makedirs(BRIEFINGS_DIR, exist_ok=True)
    md_lines = [today.get("title", ""), ""]
    md_lines += [p for p in (today.get("paragraphs") or [])]
    if region == "asia":
        md_name = today["as_of"] + "-asia.md"
        arr = upsert(load_archive(ARCHIVE_ASIA, r"window\.BRIEFINGS_ASIA"), today)
        write_archive(
            ARCHIVE_ASIA, "window.BRIEFINGS_ASIA",
            "// 아시아장 마감 후 한국어 시황 브리핑 아카이브 (newest first).\n"
            "// briefing/generate_briefing.py 가 매일(15:50 KST) 새 항목을 맨 앞에 추가한다.",
            arr)
    else:
        md_name = today["as_of"] + ".md"
        arr = upsert(load_archive(ARCHIVE_US, r"window\.BRIEFINGS"), today)
        write_archive(
            ARCHIVE_US, "window.BRIEFINGS",
            "// 미국장 마감 후 한국어 시황 브리핑 아카이브 (newest first).\n"
            "// briefing/generate_briefing.py 가 매일 새 항목을 맨 앞에 추가한다.",
            arr)
        with open(BRIEFING_DATA_US, "w", encoding="utf-8") as f:
            f.write("// 미국장 마감 후 한국어 시황 브리핑 (최신본).\n"
                    "window.BRIEFING = " +
                    json.dumps(today, ensure_ascii=False, indent=2) + ";\n")
    with open(os.path.join(BRIEFINGS_DIR, md_name), "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")
    return md_name


# ----------------------------------------------------------------------------
def gh_output(**kv):
    """GitHub Actions step output 으로 status/as_of/md 를 노출(있을 때만)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write("%s=%s\n" % (k, v))
    except Exception:
        pass


def archive_has(region, as_of):
    if region == "asia":
        arr = load_archive(ARCHIVE_ASIA, r"window\.BRIEFINGS_ASIA")
    else:
        arr = load_archive(ARCHIVE_US, r"window\.BRIEFINGS")
    return any(b.get("as_of") == as_of for b in arr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("region", choices=["asia", "us"])
    ap.add_argument("--as-of", dest="as_of", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-if-exists", action="store_true",
                    help="해당 as_of 브리핑이 아카이브에 이미 있으면 생성·발송 생략")
    ap.add_argument("--draft", action="store_true",
                    help="장중 잠정치 기반 초안 생성(아시아 전용). 아카이브 미기록, "
                         "_draft-asia.js 로 출력. 이메일 제목 [초안].")
    args = ap.parse_args()

    daily = load_daily()
    bench = load_benchmarks()
    as_of, system_prompt, user_payload = build_request(
        args.region, daily, bench, args.as_of, draft=args.draft)

    if not as_of:
        sys.stderr.write("could not determine as_of\n")
        sys.exit(3)

    # 초안은 멱등성 가드를 적용하지 않는다(항상 최신 초안 재생성·발송).
    if args.skip_if_exists and not args.draft and archive_has(args.region, as_of):
        print("skip: %s briefing for %s already exists" % (args.region, as_of))
        gh_output(status="skipped", as_of=as_of)
        return

    try:
        result = call_claude(system_prompt, user_payload)
    except Exception as e:
        sys.stderr.write("Claude API/parse failure: %s\n" % e)
        sys.exit(4)

    paragraphs = result.get("paragraphs") or []
    if not paragraphs:
        sys.stderr.write("model returned empty paragraphs\n")
        sys.exit(4)

    outlook = result.get("outlook") or []
    if isinstance(outlook, str):
        outlook = [outlook]
    outlook = [str(x).strip() for x in outlook if x and str(x).strip()][:4]

    title = result.get("title") or ""
    if args.draft and not title.rstrip().endswith("(초안)"):
        title = (title.rstrip() + " (초안)").strip()

    today = {
        "as_of": as_of,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": title,
        "paragraphs": paragraphs,
        "report": result.get("report") or {},
        "outlook": outlook,
        "draft": bool(args.draft),
    }

    if args.dry_run:
        print(json.dumps(today, ensure_ascii=False, indent=2))
        return

    if args.draft:
        # 초안: 아카이브에 기록하지 않고 _draft-asia.js 로만 출력(이메일 전용).
        with open(DRAFT_ASIA_JS, "w", encoding="utf-8") as f:
            f.write("window.BRIEFINGS_ASIA_DRAFT = " +
                    json.dumps([today], ensure_ascii=False, indent=2) + ";\n")
        print("draft:", args.region, as_of, "->", DRAFT_ASIA_JS,
              "(%d paragraphs)" % len(paragraphs))
        gh_output(status="draft", as_of=as_of)
        return

    md_name = publish(args.region, today)
    print("generated:", args.region, as_of, "->", md_name,
          "(%d paragraphs)" % len(paragraphs))
    gh_output(status="generated", as_of=as_of, md=md_name)


if __name__ == "__main__":
    main()
