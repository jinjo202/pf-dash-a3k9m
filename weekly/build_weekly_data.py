# -*- coding: utf-8 -*-
"""회의 xlsx → weekly-data.js 갱신 헬퍼.

weekly_report.py 리팩터링(load_kr_flows → load_json)으로 회의 자동화가
깨지는 것을 막는 얇은 래퍼. 사용:

    python weekly/build_weekly_data.py <meeting YYYY-MM-DD> <target YYYY-MM-DD> <xlsx경로>
"""
import sys, os, importlib.util
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("wr", os.path.join(_HERE, "weekly_report.py"))
wr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wr)


def _d(s):
    y, m, dd = s.split("-")
    return date(int(y), int(m), int(dd))


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    meeting, target, xlsx = _d(sys.argv[1]), _d(sys.argv[2]), sys.argv[3]
    kr = wr.load_json("kr_flows.json")  # 구 load_kr_flows() 대체
    wr.write_weekly_data(meeting, target, wr.load_benchmarks(), wr.load_macro(),
                         kr, wr.load_portfolio(), wr.load_daily(),
                         wr.get_sentiment(True), xlsx)
    print("weekly-data.js 갱신 완료")


if __name__ == "__main__":
    main()
