// ============================================================
// 롱숏포트 데이터 원본 — 매일 이 파일만 갱신하면 대시보드에 반영됨
// 갱신 절차: DAILY_UPDATE.md 참조
// 구조: books[0] = 전략 A (마켓 뉴트럴, STRATEGY.md)
//       books[1] = 전략 B (디렉셔널 L/S, STRATEGY_DIRECTIONAL.md)
// 가격 기준: 각 시장 최근 종가 / P&L: 현지통화 수익률 (KRW 선물환 헤지 가정)
// ============================================================
window.PORTFOLIO_DATA = {
  books: [

  // ================= 전략 A: 마켓 뉴트럴 =================
  {
    id: "neutral",
    tabLabel: "전략 A · 마켓 뉴트럴",
    meta: {
      bookName: "롱숏포트 · LS-Alpha",
      strategy: "Market Neutral Long/Short Equity (KR + S&P500 + Asia)",
      aumUsd: 10000000,
      inceptionDate: "2026-07-10",
      asOfPrice: "2026-07-10",
      lastUpdated: "2026-07-12",
      usdkrw: 1498.87,
      phase: "빌드업 Phase 1 — 페어 5개 / Gross 40% (목표 12~20개 / 180~200%)",
      // grossMaxPct/netMaxPct = 정책 상한. 운용 목표 Gross 180~200% / Net 0±5% (경보 ±10%)
      limits: { grossMaxPct: 300, netMaxPct: 50, varLimitPctNav: 1.2, factorZSoft: 0.20, factorZHard: 0.30 }
    },
    ideas: [
      {
        date: "2026-07-12",
        tag: "시장 뷰",
        title: "반도체 고점론發 조정 3주차 — 디스퍼전 확대는 뉴트럴 북의 기회",
        body: "코스피 6/22 사상최고(9,114) 후 약 20% 조정. 모건스탠리 '반도체 사이클 마무리' 코멘트와 하이닉스 시총의 삼성전자 역전(=고점 신호 담론)이 크라우디드 롱 언와인드를 촉발. 방향 베팅 없이 종목 간 낙폭 격차(7/10 하이닉스 -10.1% vs 삼성전자 -7.9%)를 수확하는 국면. 페어 #1(삼성전자 L / 하이닉스 S) 논지 유효."
      },
      {
        date: "2026-07-12",
        tag: "신규 진입",
        title: "삼성전자 우선주 괴리 31.9% — 급락장이 벌려 놓은 캐리 기회",
        body: "7/10 종가 기준 우선주 디스카운트 31.9%(우 194,300 / 보통주 285,000). 패닉 국면에서 유동성 낮은 우선주가 더 빠지며 괴리가 밴드 상단 근접. 배당 캐리 + 평균회귀를 노린 구조적 페어 #2 진입 (레그당 5%)."
      },
      {
        date: "2026-07-12",
        tag: "리스크",
        title: "이란-미국 지정학 리스크 — 넷 제로 사수, 월요일 갭 대비",
        body: "이란 보복 공습 뉴스로 사이드카 발동 이력. 오버나이트 갭 리스크가 큰 주간 — 베타 조정 넷 0 유지, 신규 진입은 장 초반 변동성 소화 후 VWAP 분할로만. 숏 다리 +15% 역행 스톱은 갭 상황에서도 기계적 집행."
      }
    ],
    navHistory: [
      { date: "2026-07-10", nav: 100.00 }
    ],
    risk: {
      grossPct: 40.0,
      netPct: 0.0,
      predictedBeta: 0.02,
      var1d99PctNav: 0.35,
      factors: [
        { name: "Market Beta", z: 0.02 },
        { name: "Size",        z: -0.05 },
        { name: "Value",       z: 0.12 },
        { name: "Momentum",    z: -0.15 },
        { name: "Quality",     z: 0.05 },
        { name: "Volatility",  z: -0.08 },
        { name: "Growth",      z: -0.10 }
      ],
      countryNets: [
        { name: "한국", netPct: -0.5 },
        { name: "미국", netPct: 0.0 },
        { name: "기타 아시아(대만)", netPct: 0.5 }
      ]
    },
    pairs: [
      {
        id: "P1", name: "K-메모리 크라우딩 언와인드", tier: 1, type: "펀더멘털",
        thesis: "하이닉스 시총 역전 이후 크라우디드 롱 언와인드 국면. 밸류에이션 갭 극단 + 외국인 매도 집중은 하이닉스 측. 삼성전자는 역대 최대 실적으로 하방 지지.",
        stopPct: -8, status: "OPEN",
        legs: [
          { side: "LONG",  ticker: "005930.KS", label: "삼성전자",   ccy: "KRW", weightPct: 4.5, entry: 285000,  last: 285000 },
          { side: "SHORT", ticker: "000660.KS", label: "SK하이닉스", ccy: "KRW", weightPct: 4.5, entry: 2180000, last: 2180000 }
        ]
      },
      {
        id: "P2", name: "삼성전자 우선주 괴리", tier: 1, type: "구조적",
        thesis: "우선주 디스카운트 31.9% — 급락장에서 괴리 확대, 역사적 밴드 상단. 배당 캐리 + 평균회귀. 시장 방향과 무상관.",
        stopPct: -8, status: "OPEN",
        legs: [
          { side: "LONG",  ticker: "005935.KS", label: "삼성전자우", ccy: "KRW", weightPct: 5.0, entry: 194300, last: 194300 },
          { side: "SHORT", ticker: "005930.KS", label: "삼성전자",   ccy: "KRW", weightPct: 5.0, entry: 285000, last: 285000 }
        ]
      },
      {
        id: "P3", name: "파운드리 — 검증된 실적 vs 선반영 기대", tier: 1, type: "펀더멘털",
        thesis: "TSMC는 선단공정 실적이 뒷받침되는 반면, 인텔은 파운드리 턴어라운드 기대가 주가에 과도 선반영(연중 랠리 후 7/10 -8.7% 급반락). 기대와 실적의 갭 축소에 베팅.",
        stopPct: -8, status: "OPEN",
        legs: [
          { side: "LONG",  ticker: "TSM",  label: "TSMC (ADR)", ccy: "USD", weightPct: 4.5, entry: 434.11, last: 434.11 },
          { side: "SHORT", ticker: "INTC", label: "Intel",      ccy: "USD", weightPct: 4.5, entry: 109.84, last: 109.84 }
        ]
      },
      {
        id: "P4", name: "US 대형 리테일 실행력 격차", tier: 2, type: "펀더멘털",
        thesis: "월마트의 이커머스·광고 수익화 vs 타깃의 트래픽 점유율 이탈. 어닝 리비전 방향이 상반 — 동일 소비 사이클 내 상대 베팅.",
        stopPct: -8, status: "OPEN",
        legs: [
          { side: "LONG",  ticker: "WMT", label: "Walmart", ccy: "USD", weightPct: 3.0, entry: 113.90, last: 113.90 },
          { side: "SHORT", ticker: "TGT", label: "Target",  ccy: "USD", weightPct: 3.0, entry: 135.14, last: 135.14 }
        ]
      },
      {
        id: "P5", name: "K-2차전지 수주 모멘텀 격차", tier: 2, type: "펀더멘털",
        thesis: "LG에너지솔루션의 북미 캐파·수주잔고 모멘텀 vs 삼성SDI의 믹스 열위. 섹터 방향(전기차 수요)은 중립화하고 상대 실적 격차만 수확.",
        stopPct: -8, status: "OPEN",
        legs: [
          { side: "LONG",  ticker: "373220.KS", label: "LG에너지솔루션", ccy: "KRW", weightPct: 3.0, entry: 326000, last: 326000 },
          { side: "SHORT", ticker: "006400.KS", label: "삼성SDI",        ccy: "KRW", weightPct: 3.0, entry: 434000, last: 434000 }
        ]
      }
    ],
    weeklyAttribution: []
  },

  // ================= 전략 B: 디렉셔널 L/S =================
  {
    id: "directional",
    tabLabel: "전략 B · 디렉셔널 L/S",
    meta: {
      bookName: "롱숏포트 · LS-D",
      strategy: "Directional Long/Short Equity — 레짐 기반 넷 익스포저 (KR + S&P500 + Asia)",
      aumUsd: 10000000,
      inceptionDate: "2026-07-10",
      asOfPrice: "2026-07-10",
      lastUpdated: "2026-07-12",
      usdkrw: 1498.87,
      phase: "레짐: 중립(Neutral) — 넷 +45% / β 0.46 · 강세 복귀 시 +50~60% (일 +3%p 램프)",
      // 넷 밴드: 강세 +50~60(캡 +70) / 중립 +30~45 / 경계 +10~25 / 위기 -10~+10
      limits: { grossMaxPct: 300, netMaxPct: 70, varLimitPctNav: 1.8, factorZSoft: 0.35, factorZHard: 0.50 }
    },
    ideas: [
      {
        date: "2026-07-12",
        tag: "레짐 판정",
        title: "중립(Neutral) 확정 — 넷 +45%, β 0.46로 출발",
        body: "실측 신호(7/10): VIX 15.0(강세), S&P500 50/200DMA 상회(강세), 그러나 KOSPI가 3주 -18% 급락으로 50DMA(7,965) 하향 이탈(중립 강등). 합성 판정 '중립' → 넷 밴드 +30~45%의 상단인 +45%로 시딩. KOSPI 50DMA 회복 + VIX<20 유지 시 주당 +15%p 램프로 강세 밴드(+50~60%) 증량."
      },
      {
        date: "2026-07-12",
        tag: "시장 뷰",
        title: "롱북은 '조정에서 살아남을 고β 리더' — 낙폭과대 추격은 금지",
        body: "반도체 고점론 조정 국면에서 롱북은 실적이 검증된 리더(삼성전자·TSMC·LG엔솔)로 한정하고, 숏북(Intel·Target·삼성SDI)은 하락장에서 더 빠지는 구조적 열위 종목으로 다운사이드 헤지를 겸하게 구성. 부족한 넷은 지수선물(KOSPI200+ES 각 10%)로 채워 알파 포지션 훼손 없이 방향 노출만 확보."
      },
      {
        date: "2026-07-12",
        tag: "리스크",
        title: "VIX 15의 안이함을 경계 — 자동 헤지 트리거 상기",
        body: "이란-미국 지정학 리스크에도 VIX 15는 컴플레이슨시 신호일 수 있음. 기계 트리거 상기: VIX 일중 +5pt 또는 30 돌파 → 당일 선물로 넷 50% 헤지. 일간 -2% → 익일 넷 50% 인하. 월중 -6% → 넷 0(뉴트럴 전환). 재량 개입 없음."
      }
    ],
    navHistory: [
      { date: "2026-07-10", nav: 100.00 }
    ],
    risk: {
      grossPct: 71.0,
      netPct: 45.0,
      predictedBeta: 0.46,
      var1d99PctNav: 1.25,   // 추정 모델: √[(Gross71×0.88bp)² + (β0.46×2.33×1.0%)²] — 알파 0.63 + 방향성 1.07
      factors: [
        { name: "Market Beta", z: 0.46 },
        { name: "Size",        z: 0.10 },
        { name: "Value",       z: -0.10 },
        { name: "Momentum",    z: 0.30 },
        { name: "Quality",     z: 0.25 },
        { name: "Volatility",  z: -0.12 },
        { name: "Growth",      z: 0.28 }
      ],
      countryNets: [
        { name: "한국", netPct: 28.0 },
        { name: "미국", netPct: 8.0 },
        { name: "기타 아시아(대만)", netPct: 9.0 }
      ]
    },
    // 디렉셔널 북은 '페어'가 아니라 포지션 그룹. stopPct: null = 그룹 스톱 없음(개별 규율 적용:
    // 롱 -15% 손절 / 숏 +15% 커버. 오버레이는 레짐 규칙으로만 증감)
    pairs: [
      {
        id: "G1", name: "코어 롱 — 고β 리더", tier: 1, type: "롱북",
        thesis: "구조적 성장 산업의 검증된 1등주 (β 1.1~1.4). 상승 참여 엔진. 어닝 리비전 상향 유지되는 한 보유.",
        stopPct: null, status: "OPEN",
        legs: [
          { side: "LONG", ticker: "005930.KS", label: "삼성전자 (β1.10)",       ccy: "KRW", weightPct: 10.0, entry: 285000, last: 285000 },
          { side: "LONG", ticker: "TSM",       label: "TSMC ADR (β1.15)",      ccy: "USD", weightPct: 9.0,  entry: 434.11, last: 434.11 },
          { side: "LONG", ticker: "373220.KS", label: "LG에너지솔루션 (β1.40)", ccy: "KRW", weightPct: 6.0,  entry: 326000, last: 326000 }
        ]
      },
      {
        id: "G2", name: "밸러스트 롱 — 저β 캐리", tier: 2, type: "롱북",
        thesis: "넷을 유지하면서 포트 β를 목표 밴드(0.4~0.6) 안으로 눌러주는 방어 캐리 (β 0.65~0.95).",
        stopPct: null, status: "OPEN",
        legs: [
          { side: "LONG", ticker: "WMT",       label: "Walmart (β0.65)",    ccy: "USD", weightPct: 7.0, entry: 113.90, last: 113.90 },
          { side: "LONG", ticker: "005935.KS", label: "삼성전자우 (β0.95)", ccy: "KRW", weightPct: 6.0, entry: 194300, last: 194300 }
        ]
      },
      {
        id: "G3", name: "알파 숏 — 구조적 열위", tier: 1, type: "숏북",
        thesis: "기대 선반영·점유율 이탈·믹스 열위 종목 (β 0.9~1.15). 하락장에서 시장보다 더 빠지며 다운사이드 헤지를 겸함.",
        stopPct: null, status: "OPEN",
        legs: [
          { side: "SHORT", ticker: "INTC",      label: "Intel (β1.10)",    ccy: "USD", weightPct: 5.0, entry: 109.84, last: 109.84 },
          { side: "SHORT", ticker: "TGT",       label: "Target (β0.90)",   ccy: "USD", weightPct: 4.0, entry: 135.14, last: 135.14 },
          { side: "SHORT", ticker: "006400.KS", label: "삼성SDI (β1.15)",  ccy: "KRW", weightPct: 4.0, entry: 434000, last: 434000 }
        ]
      },
      {
        id: "G4", name: "지수 오버레이 — 레짐 스케일링 전용", tier: 1, type: "오버레이",
        thesis: "중립 레짐 넷 목표(+45%)와 종목 넷(+25%)의 갭을 선물로 충당. 레짐 전환·손실 사다리 발동 시 이 그룹만 증감 — 종목 알파에 손대지 않는다.",
        stopPct: null, status: "OPEN",
        legs: [
          { side: "LONG", ticker: "^KS11", label: "KOSPI200 선물 (지수 프록시)", ccy: "KRW", weightPct: 10.0, entry: 7475.9, last: 7475.9 },
          { side: "LONG", ticker: "^GSPC", label: "S&P500 E-mini (지수 프록시)", ccy: "USD", weightPct: 10.0, entry: 7575.4, last: 7575.4 }
        ]
      }
    ],
    weeklyAttribution: []
  }

  ]
};
