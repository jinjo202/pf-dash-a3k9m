// 오늘의 CIO 데일리 — briefing/generate_cio.py 가 자동 생성 (직접 편집 금지).
// 사고 흐름(chain)·정성 요인(factors)·포지셔닝 결론. newest-first, 30개 유지.
window.FM_CIO = {
  "updated_utc": "2026-07-03T11:25:51Z",
  "entries": [
    {
      "as_of": "2026-07-03",
      "slot": "asia_close",
      "generated_utc": "2026-07-03T11:25:51Z",
      "headline": "메모리 반발 매수에 KOSPI 5.8% 급등, 필라 반도체는 조정 지속",
      "market_pulse": "KOSPI 8088(+5.76%), 정보기술 +7.77%로 급반등. SK하이닉스 +10.88%, 삼성전자 +8.22% — 기관 역대 최대 4.4조원 순매수. 미국 6월 고용 +5.7만(예상 +11만 하회)으로 금리 인상 기대 완화. 반면 필라델피아 반도체 -5.44%, MTD -11.38% 조정 심화. NASDAQ -0.80%, 다우 +1.14%로 섹터 양극화.",
      "changes": "초기 작성. 전일 entry 없음.",
      "chain": [
        {
          "issue": "마이크론 FQ3'26 어닝 서프라이즈",
          "date": "6/24",
          "nature": "fundamental",
          "verdict": "pos",
          "read": "매출 4배·DRAM ASP +32% QoQ로 HBM·DRAM 가격 강세 확인. 메모리 슈퍼사이클이 실적으로 증명됨.",
          "action": "삼성전자·SK하이닉스 비중 유지/확대 정당화"
        },
        {
          "issue": "칩플레이션: 애플 Mac·iPad 가격 인상",
          "date": "6월",
          "nature": "mixed",
          "verdict": "watch",
          "read": "메모리 원가 급등을 세트가로 전가. 메모리 타이트 확증이자 세트 수요 탄력성 리스크. 애플 -6% 반응.",
          "action": "메모리 업스트림 강화 / 세트 수요 민감도 모니터"
        },
        {
          "issue": "OpenAI 상장 2027 연기",
          "date": "6/26",
          "nature": "technical",
          "verdict": "neg",
          "read": "AI 1차 대형 유동성 이벤트 지연. 센티먼트 부담이나 capex 펀더멘털과는 별개.",
          "action": "AI 익스포저 센티먼트 변동성 요인으로 관리"
        },
        {
          "issue": "필라델피아 반도체 조정 심화",
          "date": "7/2~7/3",
          "nature": "technical",
          "verdict": "watch",
          "read": "MTD -11.38%, 일간 -5.44%. AI 수요 냉각 우려 vs. 메모리 펀더멘털 괴리. 한·미 반도체 디커플링.",
          "action": "조정을 technical로 판정 시 매수 기회 / 펀더멘털 훼손 징후 점검"
        },
        {
          "issue": "미국 6월 고용 쇼크 (+5.7만)",
          "date": "7/2",
          "nature": "fundamental",
          "verdict": "pos",
          "read": "예상 +11만 대비 절반. 금리 인상 기대 급락 → VIX -1.05%, 금리 부담 완화로 위험자산 반등 촉매.",
          "action": "성장주·반도체 멀티플 부담 완화. 한국 저가 매수 환경"
        },
        {
          "issue": "한국 기관 역대 최대 매수 (4.4조원)",
          "date": "7/3",
          "nature": "technical",
          "verdict": "pos",
          "read": "반도체 급락 후 국민연금 등 기관 대규모 반발 매수. KOSPI +5.76% 주도. Technical 반전 신호.",
          "action": "한국 메모리 저가 진입 지속"
        }
      ],
      "factors": [
        {
          "date": "7/2",
          "tag": "매크로",
          "dir": "pos",
          "title": "미국 6월 고용 +5.7만, 금리 인상 기대 완화",
          "detail": "비농업고용 +5.7만(예상 +11만). 연준 금리 인상 기대 급락 → US 10Y -0.46%, VIX -1.05%.",
          "implication": "성장주·반도체 멀티플 부담 완화. 한국 메모리 저가 매수 환경 조성.",
          "affected": [
            "005930.KS",
            "000660.KS",
            "NVDA",
            "AVGO"
          ]
        },
        {
          "date": "7/3",
          "tag": "메모리|수급",
          "dir": "pos",
          "title": "한국 기관 역대 최대 4.4조 순매수, 메모리 반발",
          "detail": "KOSPI 정보기술 +7.77%, SK하이닉스 +10.88%, 삼성전자 +8.22%. 기관 4.4조 매수로 반등 주도.",
          "implication": "전일 급락 후 technical 반발. 메모리 펀더멘털(마이크론 서프라이즈) 믿고 저가 진입 지속 정당화.",
          "affected": [
            "005930.KS",
            "000660.KS"
          ]
        },
        {
          "date": "7/2",
          "tag": "AI밸류|빅테크FCF",
          "dir": "watch",
          "title": "메타-삼성파운드리 $6.5B AI칩(MTIA) 계약 보도",
          "detail": "SeekingAlpha: 메타가 자체 AI칩 MTIA를 삼성파운드리에 $6.5B 규모 발주. 메타 -4.90%.",
          "implication": "빅테크 AI capex 지속 확인(우호). 동시에 자체칩 전환 → GPU 의존 감소 우려(NVDA 리스크). 삼성파운드리 수혜.",
          "affected": [
            "META",
            "NVDA",
            "005930.KS"
          ]
        },
        {
          "date": "7/2~7/3",
          "tag": "반도체",
          "dir": "neg",
          "title": "필라델피아 반도체 -5.44%, MTD -11.38%",
          "detail": "미국 반도체 지수 조정 심화. AI 수요 냉각 우려 vs. 한국 메모리 반등 디커플링.",
          "implication": "미국 반도체 조정이 technical(수급)인지 fundamental(수요 훼손)인지 판별 필요. 한국은 메모리 펀더멘털 믿고 매수.",
          "affected": [
            "NVDA",
            "AVGO",
            "AMD"
          ]
        },
        {
          "date": "7/3",
          "tag": "수급",
          "dir": "pos",
          "title": "USD/KRW -1.33% → 1531원, 당국 개입 추정",
          "detail": "외환당국 스무딩 오퍼레이션 추정. 6/17 이후 최저. 24시간 외환시장 개장(7/6) 대비 야간 모니터링 강화.",
          "implication": "원화 강세 → 한국 주식 외국인 매수 유인. 환율 안정 → 수출주(반도체·조선) 실적 가시성.",
          "affected": [
            "005930.KS",
            "000660.KS",
            "329180.KS"
          ]
        }
      ],
      "positioning": {
        "macro_view": "미국 고용 쇼크로 금리 인상 기대 완화 → 성장주 멀티플 부담 해소. 한국 메모리는 미국 반도체 조정과 디커플링하며 technical 반발. 원화 강세·기관 매수로 수급 우호.",
        "equity_weight": {
          "stance": "확대",
          "text": "메모리 펀더멘털(마이크론 서프라이즈) 건재한 가운데 technical 조정 반전 신호. 금리 부담 완화로 순노출 확대 국면."
        },
        "country": "한국 비중 유지/확대. 메모리 반발·원화 강세·기관 매수 트리플 호재. 미국은 필라 반도체 조정 지켜보며 선별 — AI capex 지속 종목(NVDA·AVGO) 코어 유지.",
        "sector": "정보기술(메모리·AI 컴퓨트) overweight 유지. 산업재(조선·원전) 원화 강세 수혜. 커뮤니케이션(메타 자체칩) watch — AI capex는 지속이나 GPU 의존 감소 리스크.",
        "trades": [
          {
            "action": "비중확대",
            "ticker": "005930.KS",
            "name": "삼성전자",
            "reason": "메모리 반발 +8.22%, 메타 파운드리 수주로 AI capex 지속 확인. 칩플레이션 업스트림 수혜."
          },
          {
            "action": "유지",
            "ticker": "000660.KS",
            "name": "SK하이닉스",
            "reason": "+10.88% 급등. HBM 펀더멘털 믿고 코어 유지. 미래에셋 1.26조 CP 인수 참여는 중립(재무 이벤트)."
          },
          {
            "action": "유지",
            "ticker": "NVDA",
            "name": "엔비디아",
            "reason": "필라 반도체 조정 속 코어 유지. 메타 자체칩 전환은 장기 리스크나 AI capex 총량은 확대 중. 조정 시 추가 매수."
          },
          {
            "action": "유지",
            "ticker": "AVGO",
            "name": "브로드컴",
            "reason": "AI 네트워킹·ASIC 펀더멘털 건재. 필라 조정을 technical로 판정 — 매수 기회 대기."
          },
          {
            "action": "관망",
            "ticker": "META",
            "name": "메타",
            "reason": "-4.90%. 자체칩 $6.5B 발주는 AI capex 지속 증거나, GPU 의존 감소·'컴퓨팅 과잉' 발언으로 단기 부담. 실적 확인 후 재진입."
          }
        ]
      },
      "conclusion": "오늘은 메모리 펀더멘털(마이크론 서프라이즈)을 믿고 technical 조정을 매수한 한국 기관의 판단이 옳았음을 확인. 삼성전자·SK하이닉스 비중 유지/확대하며 필라 반도체 조정을 디커플링 기회로 활용. 미국 고용 쇼크로 금리 부담 완화 → 순노출 확대. 다만 ① 필라 반도체 조정이 fundamental로 전환(AI 수요 실질 냉각) 징후, ② 칩플레이션이 세트 수요를 실제 꺾는 데이터, ③ 빅테크 자체칩 전환 가속(GPU capex 감소) 신호 포착 시 디리스킹."
    }
  ]
};
