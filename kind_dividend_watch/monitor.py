"""핵심 모니터링 로직: DART 조회 → 8종목·배당키워드 필터 → 중복제거 → 메일.

상태(중복방지)는 state.json 의 'sent' 배열(rcept_no 기준)에 보관.
"""

import json
import os
from datetime import datetime, timedelta, timezone


def _now() -> datetime:
    """KST(UTC+9) 현재시각(naive). 러너는 UTC라 날짜·오전판정에 필수."""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=9)

from dart_client import DartApiClient, Disclosure
import dart_doc
import etf_watchlist
import kind_etf
import mailer
import watchlist

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
REMINDERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reminders.json")


def _load_reminders() -> list:
    if os.path.exists(REMINDERS_PATH):
        try:
            with open(REMINDERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_reminders(items: list) -> None:
    # 기준일이 30일 이상 지난 항목은 정리
    cutoff = (_now() - timedelta(days=30)).strftime("%Y-%m-%d")
    items = [r for r in items if r.get("record_date", "9999") >= cutoff]
    with open(REMINDERS_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def register_reminder(reminders: list, *, name: str, code: str, record_date: str,
                      amount: str, pay_date: str | None, rcept_no: str) -> None:
    """미래 기준일이면 리마인드 등록(중복 rcept_no는 무시)."""
    if not record_date:
        return
    today = _now().strftime("%Y-%m-%d")
    if record_date <= today:            # 공시 시점에 이미 기준일 지남 → 리마인드 불필요
        return
    if any(r.get("rcept_no") == rcept_no for r in reminders):
        return
    reminders.append({
        "rcept_no": rcept_no, "name": name, "code": code,
        "record_date": record_date, "amount": amount, "pay_date": pay_date,
        "sent_stages": [],
    })


def check_reminders(reminders: list, *, smtp_user, smtp_pass, sender, recipients,
                    dry_run: bool) -> int:
    """오전에 T-1·당일 리마인드 발송. 반환=발송 건수."""
    now = _now()
    today = now.strftime("%Y-%m-%d")
    # '당일 오전'만: 08~11시. (스케줄 첫 사이클 08:13에 포착)
    if not (8 <= now.hour <= 11):
        return 0
    sent = 0
    for r in reminders:
        rd = r.get("record_date")
        if not rd:
            continue
        try:
            d1 = (datetime.strptime(rd, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            continue
        stage = None
        if today == d1 and "d1" not in r["sent_stages"]:
            stage = "d1"
        elif today == rd and "d0" not in r["sent_stages"]:
            stage = "d0"
        if not stage:
            continue
        subject = mailer.build_reminder_subject(r, stage)
        if dry_run:
            print(f"   🧪 [DRY-RUN] 리마인드 생략: {subject}")
            r["sent_stages"].append(stage)
            sent += 1
            continue
        if mailer.send_email(smtp_user, smtp_pass, sender, recipients,
                             subject, mailer.build_reminder_body(r, stage)):
            r["sent_stages"].append(stage)
            sent += 1
    return sent


def _load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data.get("sent"), list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"sent": []}


def _save_state(state: dict) -> None:
    # sent 배열 상한(최근 2000건) — 무한 증가 방지
    if len(state.get("sent", [])) > 2000:
        state["sent"] = state["sent"][-2000:]
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def find_matches(dart: DartApiClient, days: int) -> list[Disclosure]:
    """최근 `days`일 거래소공시(I) 중 14종목의 배당/분배 공시를 반환.

    종목별 키워드(watchlist.get_keywords)로 매칭한다.
    13개는 '현금ㆍ현물배당결정', 맥쿼리인프라는 '주주명부폐쇄기간또는기준일설정'.
    """
    end = _now()
    begin = end - timedelta(days=max(0, days - 1))
    begin_s, end_s = begin.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    # corp_code → (종목명, 키워드리스트)
    corp_rules: dict[str, tuple[str, list[str]]] = {}
    for sc in watchlist.get_stock_codes():
        cc = dart.get_corp_code(sc)
        if cc:
            corp_rules[cc] = (watchlist.get_stock_name(sc), watchlist.get_keywords(sc))
        else:
            print(f"   ⚠️ corp_code 매핑 실패: {watchlist.get_stock_name(sc)} ({sc})")

    # ⚠️ 배당결정/기준일설정 모두 '거래소공시(I)'다. 주요사항보고(B)로 조회하면 0건 → 반드시 'I'.
    print(f"🔍 {begin_s}~{end_s} 거래소공시(I) 조회 중...")
    all_disc = dart.fetch_all(begin_s, end_s, pblntf_ty="I")
    print(f"   총 {len(all_disc)}건 조회")

    matches = []
    for d in all_disc:
        rule = corp_rules.get(d.corp_code)
        if rule and any(kw in d.report_nm for kw in rule[1]):
            matches.append(d)
    return matches


def find_etf_matches(days: int) -> list[tuple[str, "kind_etf.EtfDisclosure"]]:
    """최근 `days`일 KIND ETF 분배 공시 중 보유 6종목 매치 → (종목코드, 공시) 리스트."""
    end = _now()
    begin = end - timedelta(days=max(0, days - 1))
    frm, to = begin.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    print(f"🔍 {frm}~{to} KIND ETF 분배공시 조회 중...")
    out: list[tuple[str, kind_etf.EtfDisclosure]] = []
    seen_acpt: set[str] = set()
    for etf_name in etf_watchlist.current_etfs().values():
        try:
            rows = kind_etf.fetch_distributions(frm, to, etf_name=etf_name)
        except Exception as e:
            print(f"   ⚠️ ETF '{etf_name}' 조회 실패(계속): {e}")
            continue
        for d in rows:
            code = etf_watchlist.find_matched_etf(d.stock_name)
            if code and d.acptno not in seen_acpt:
                seen_acpt.add(d.acptno)
                out.append((code, d))
    print(f"   ETF 분배 매치 {len(out)}건")
    return out


def run_cycle(
    dart: DartApiClient,
    *,
    smtp_user: str,
    smtp_pass: str,
    sender: str,
    recipients: list[str],
    days: int = 1,
    dry_run: bool = False,
) -> int:
    """1회 사이클. 신규 매치 발송 + 기준일 리마인드. 반환=신규 발송 건수."""
    state = _load_state()
    reminders = _load_reminders()
    already = {s["rcept_no"] for s in state["sent"] if "rcept_no" in s}

    matches = find_matches(dart, days)
    new_items = [d for d in matches if d.rcept_no not in already]

    print(f"📋 배당결정 매치 {len(matches)}건 (신규 {len(new_items)}건)")
    for d in matches:
        flag = "🆕" if d.rcept_no in {n.rcept_no for n in new_items} else "✓이미발송"
        print(f"   {flag} {d}")

    sent_count = 0
    for d in new_items:
        subject = mailer.build_subject(d)
        # 원문(document.xml)에서 1주당 배당금·기준일·사유 등 상세 추출(실패해도 계속)
        extra = dart_doc.fetch_detail(dart.api_key, d.rcept_no)
        if dry_run:
            print(f"   🧪 [DRY-RUN] 발송 생략: {subject} → {recipients}")
            if extra:
                print(f"       상세: {extra}")
            continue
        ok = mailer.send_email(
            smtp_user, smtp_pass, sender, recipients,
            subject, mailer.build_html_body(d, extra),
        )
        if ok:
            state["sent"].append({
                "rcept_no": d.rcept_no,
                "corp_name": d.corp_name,
                "report_nm": d.report_nm,
                "rcept_dt": d.rcept_dt,
                "sent_at": _now().isoformat(timespec="seconds"),
            })
            sent_count += 1
            # 기준일이 공시일과 달라(미래) 리마인드 등록 (T-1·당일)
            rec = extra.get("배당기준일") or extra.get("기준일")
            per = extra.get("1주당 배당금")
            register_reminder(
                reminders, name=d.corp_name.strip(), code=d.stock_code,
                record_date=rec, amount=(f"₩{per}" if per else "-"),
                pay_date=extra.get("지급예정일"), rcept_no=d.rcept_no,
            )

    # ── ETF 분배 공시 (KIND) ──
    try:
        etf_matches = find_etf_matches(days)
    except Exception as e:
        print(f"⚠️ ETF 조회 오류(계속): {e}")
        etf_matches = []
    etf_new = [(c, d) for c, d in etf_matches if d.acptno not in already]
    print(f"📋 ETF 분배 매치 {len(etf_matches)}건 (신규 {len(etf_new)}건)")
    for code, d in etf_new:
        etf_name = etf_watchlist.get_etf_name(code)
        subject = mailer.build_etf_subject(etf_name, d.report_nm)
        if dry_run:
            print(f"   🧪 [DRY-RUN] ETF 발송 생략: {subject} → {recipients}")
            continue
        ok = mailer.send_email(
            smtp_user, smtp_pass, sender, recipients,
            subject, mailer.build_etf_html_body(etf_name, code, d.report_nm, d.date_str, d.acptno),
        )
        if ok:
            state["sent"].append({
                "rcept_no": d.acptno,          # ETF는 KIND acptno를 고유 id로 사용
                "corp_name": etf_name,
                "report_nm": d.report_nm,
                "rcept_dt": d.date_str,
                "kind": "etf",
                "sent_at": _now().isoformat(timespec="seconds"),
            })
            sent_count += 1

    if sent_count and not dry_run:
        _save_state(state)

    # ── 기준일 T-1·당일 리마인드 (오전) ──
    rem_sent = check_reminders(
        reminders, smtp_user=smtp_user, smtp_pass=smtp_pass, sender=sender,
        recipients=recipients, dry_run=dry_run,
    )
    if rem_sent:
        print(f"⏰ 기준일 리마인드 {rem_sent}건 발송")
    if not dry_run:
        _save_reminders(reminders)

    return sent_count
