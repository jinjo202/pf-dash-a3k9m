#!/usr/bin/env python3
"""KIND/DART 배당공시 메일러 — 진입점.

사용법:
    python run.py --test            # DART 연결 + 8종목 매핑 + 최근 매치 점검 (메일 발송 없음)
    python run.py --once --dry-run  # 1회 사이클, 발송 직전까지 (실제 메일 X)
    python run.py --once            # 1회 사이클 + 실제 발송 (cron용)
    python run.py --loop            # 상시 데몬 (POLL_INTERVAL_MINUTES 간격)

설정은 .env 에서 로드(.env.example 참고).
"""

import argparse
import io
import os
import sys
import time

# Windows cp949 콘솔에서 한글 깨짐 방지 (콘솔이 있을 때만)
if getattr(sys.stdout, "buffer", None) and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# pythonw(콘솔 없음)로 cron 실행 시에도 로그가 남도록 run.log에 tee
_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.log")


class _Tee:
    def __init__(self, stream):
        self.stream = stream
        self.log = open(_LOG_PATH, "a", encoding="utf-8", buffering=1)

    def write(self, msg):
        try:
            if self.stream:
                self.stream.write(msg)
        except Exception:
            pass
        self.log.write(msg)

    def flush(self):
        try:
            if self.stream:
                self.stream.flush()
        except Exception:
            pass
        self.log.flush()


sys.stdout = _Tee(sys.stdout)
sys.stderr = _Tee(sys.stderr)
from datetime import datetime as _dt
print(f"\n──── run {_dt.now().strftime('%Y-%m-%d %H:%M:%S')} ────")

from dotenv import load_dotenv

import mailer
import monitor
import sync_watchlist
import watchlist
import etf_watchlist
from dart_client import DartApiClient

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def _require(key: str) -> str:
    v = os.getenv(key)
    if not v:
        print(f"❌ .env 설정 누락: {key}", file=sys.stderr)
        sys.exit(1)
    return v


def _recipients() -> list[str]:
    raw = os.getenv("RECIPIENT_EMAILS", "")
    return [e.strip() for e in raw.split(",") if e.strip()]


def cmd_test() -> None:
    print("🧪 동기화 + DART 연결 + 매핑 테스트")
    res = sync_watchlist.sync()
    if res.get("ok"):
        print(f"🔄 동기화 OK (보유기준 {res['derived'].get('source_updated')}), 변경={res.get('changed')}")
        if res["derived"].get("warnings"):
            print(f"   ⚠️ {res['derived']['warnings']}")
    else:
        print(f"⚠️ 동기화 실패: {res.get('error')} → 고정/폴백 사용")

    dart = DartApiClient(api_key=_require("DART_API_KEY"))
    dart.initialize()
    codes = watchlist.get_stock_codes()
    print(f"\n🎯 주식 {len(codes)}종목 corp_code 매핑:")
    for sc in codes:
        cc = dart.get_corp_code(sc)
        print(f"   {'✅' if cc else '⚠️'} {watchlist.get_stock_name(sc)} ({sc}) → {cc or '실패'}")
    etfs = etf_watchlist.current_etfs()
    print(f"\n📦 감시 ETF {len(etfs)}종(보유 자동추종):")
    for c, n in etfs.items():
        print(f"   • {n} ({c})")
    dart.close()
    print("\n✅ 테스트 완료")


def _make_dart() -> DartApiClient:
    dart = DartApiClient(api_key=_require("DART_API_KEY"))
    dart.initialize()
    return dart


def _sync_and_notify(recipients: list[str], dry_run: bool) -> None:
    """보유종목 → 감시대상 동기화. 변경 시 알림 메일."""
    res = sync_watchlist.sync()
    if not res.get("ok"):
        print(f"⚠️ 감시대상 동기화 건너뜀: {res.get('error')} (직전 목록/폴백 사용)")
        return
    d = res.get("diff", {})
    warns = res.get("derived", {}).get("warnings", [])
    if res.get("changed"):
        print(f"🔄 감시대상 변경 감지: {d}")
        if warns:
            print(f"   ⚠️ {warns}")
        if not dry_run:
            lines = []
            if d.get("etf_added"):   lines.append("ETF 추가: " + ", ".join(d["etf_added"]))
            if d.get("etf_removed"): lines.append("ETF 제외: " + ", ".join(d["etf_removed"]))
            if d.get("stock_added"): lines.append("주식 추가: " + ", ".join(d["stock_added"]))
            if d.get("stock_removed"): lines.append("주식 제외(고정목록은 유지): " + ", ".join(d["stock_removed"]))
            body = ("<div style=\"font-family:'Malgun Gothic',sans-serif;font-size:14px\">"
                    "<h3>🔄 배당·분배 감시대상 자동 업데이트</h3><ul>"
                    + "".join(f"<li>{x}</li>" for x in lines) + "</ul>"
                    + ("<p style='color:#c00'>⚠️ " + "<br>".join(warns) + "</p>" if warns else "")
                    + "<p style='color:#888;font-size:12px'>포트폴리오 보유 변경에 따라 자동 반영됨.</p></div>")
            mailer.send_email(_require("SMTP_USER"), _require("SMTP_PASS"),
                              os.getenv("SENDER_EMAIL", _require("SMTP_USER")), recipients,
                              "[감시대상 변경] 배당·분배 모니터링 자동 업데이트", body)
    else:
        print("🔄 감시대상 변동 없음")


def _kst_now():
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=9)


def _market_gate() -> bool:
    """MARKET_HOURS_ONLY=1(러너)이면 KST 평일 08~20시만 통과. FORCE_RUN이면 무시(테스트)."""
    if os.getenv("FORCE_RUN", "") in ("1", "true", "True"):
        return True
    if os.getenv("MARKET_HOURS_ONLY", "") not in ("1", "true", "True"):
        return True
    now = _kst_now()
    if now.weekday() >= 5:            # 토·일
        print(f"⏸️  주말(KST {now:%Y-%m-%d %H:%M}) — 스킵")
        return False
    if not (8 <= now.hour <= 20):
        print(f"⏸️  장시간 외(KST {now:%H:%M}) — 스킵")
        return False
    return True


def cmd_once(dry_run: bool) -> None:
    if not _market_gate():
        return
    recipients = _recipients()
    if not recipients:
        print("❌ RECIPIENT_EMAILS 미설정", file=sys.stderr)
        sys.exit(1)
    _sync_and_notify(recipients, dry_run)
    dart = _make_dart()
    n = monitor.run_cycle(
        dart,
        smtp_user=_require("SMTP_USER"),
        smtp_pass=_require("SMTP_PASS"),
        sender=os.getenv("SENDER_EMAIL", _require("SMTP_USER")),
        recipients=recipients,
        days=int(os.getenv("LOOKBACK_DAYS", "1")),
        dry_run=dry_run,
    )
    dart.close()
    print(f"\n{'🧪 DRY-RUN' if dry_run else '✅'} 사이클 종료 — 신규 발송 {n}건")


def cmd_loop(dry_run: bool) -> None:
    interval = int(os.getenv("POLL_INTERVAL_MINUTES", "5"))
    print(f"♻️  상시 모니터링 시작 (간격 {interval}분, dry_run={dry_run})")
    while True:
        try:
            cmd_once(dry_run)
        except Exception as e:
            print(f"⚠️ 사이클 오류(계속): {e}", file=sys.stderr)
        time.sleep(interval * 60)


def main() -> None:
    p = argparse.ArgumentParser(description="KIND/DART 배당공시 메일러")
    p.add_argument("--test", action="store_true", help="연결/매핑/매치 점검(발송 없음)")
    p.add_argument("--once", action="store_true", help="1회 사이클(cron용)")
    p.add_argument("--loop", action="store_true", help="상시 데몬")
    p.add_argument("--dry-run", action="store_true", help="실제 발송 생략")
    a = p.parse_args()

    if a.test:
        cmd_test()
    elif a.loop:
        cmd_loop(a.dry_run)
    elif a.once:
        cmd_once(a.dry_run)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
