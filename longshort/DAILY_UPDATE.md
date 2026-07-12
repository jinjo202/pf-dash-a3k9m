# 일일 업데이트 런북 (Claude용)

매일 "업데이트해줘" 한 마디로 실행되는 절차. 모든 결과는 `data.js` 한 파일에만 기록한다.
**두 북 모두 갱신한다**: `books[0]` = 전략 A (마켓 뉴트럴), `books[1]` = 전략 B (디렉셔널 L/S).

## 절차

1. **시세 수집** — `powershell -File update-prices.ps1` 실행 (종목 + ^KS11/^GSPC/^VIX + USDKRW).
   - 주말/휴장일이면 마지막 거래일 종가가 나온다. `data.js`의 `meta.asOfPrice`와 같은 날짜면 "시장 휴장, NAV 변동 없음"으로 처리하고 아이디어만 갱신.
1-B. **전략 B 레짐 판정** — 아래 파이썬으로 신호 산출 후 STRATEGY_DIRECTIONAL.md §1 매트릭스로 판정:
   `python -c "import backtest as bt; [print(t, list(sorted(bt.fetch(t,2).items()))[-1], 'MA50/200:', round(bt.sma_series(bt.fetch(t,2),50)[max(bt.sma_series(bt.fetch(t,2),50))],1)) for t in ['^VIX','^KS11','^GSPC']]"` (또는 update-prices 출력 + 수동 MA 확인)
   - 레짐 변경/트리거(200DMA 돌파·이탈, VIX 30/40, 일간 −2%, 월중 −4%/−6%) 발생 시: G4 오버레이 weightPct 조정으로 넷을 목표 밴드에 맞추고, `meta.phase`와 아이디어 카드(태그 '레짐 판정')에 기록. 증액은 주 +15%p 램프 준수.
2. **data.js 갱신**
   - 각 레그의 `last`를 새 종가로 교체, `meta.asOfPrice`·`meta.lastUpdated`·`meta.usdkrw` 갱신.
   - NAV 계산: `당일 NAV 변동(%p) = Σ_open pairs Σ_legs weightPct × side부호 × (신규last/직전last − 1)`
     (side부호: 롱 +1, 숏 −1. 직전 last는 어제 data.js에 있던 값). `navHistory`에 `{date, nav}` 한 줄 추가 (nav = 직전 nav × (1 + 변동/100), 소수 2자리).
3. **리스크 스냅샷 갱신** — `risk.grossPct/netPct`는 가격 변동에 따른 드리프트 반영(레그 weightPct × (last/entry)). 팩터 z값은 정밀 모델이 없으므로 포지션 구성이 바뀐 날만 방향성 있게 조정.
4. **룰 점검 (STRATEGY.md §3)** — 기계적으로 체크하고 해당 시 아이디어 카드에 경보 게시:
   - 페어 P&L ≤ −8% (그로스 대비) → 50% 축소 기록 (`weightPct` 절반, 아이디어에 사유)
   - 숏 레그 진입 대비 +15% 역행 → 50% 커버 기록
   - 월중 NAV −3% → 전 페어 weightPct 50% 감축
   - 일간 −1.5% → "신규 동결" 배지
5. **오늘의 아이디어 작성** — 웹 검색으로 시장 이슈(코스피/미국/반도체/지정학) 확인 후 `ideas` 배열 맨 앞에 오늘 날짜로 2~3개 추가. 태그: `시장 뷰` / `신규 진입` / `청산` / `리스크`. 기존 카드는 남겨둔다(대시보드는 최신 날짜만 노출).
6. **주간(금요일) 어트리뷰션** — `weeklyAttribution`에 알파/팩터 분해(근사: 페어 스프레드 P&L=알파, 넷 익스포저×시장수익률=팩터), 롱북/숏북 bps, hit rate(이익 페어 비율), 한 줄 메모 추가.
7. **포지션 변경 규칙** — 신규 페어 추가/청산은 아이디어 카드에 논지와 함께 기록. 신규 진입은 `entry`=당일 종가. 청산은 `status:"CLOSED"`로 두고 그로스 합산에서 제외됨(코드가 OPEN만 합산).
8. **검증** — 로컬에서 `python -m http.server 8787` 후 `http://127.0.0.1:8787/index.html` 열어 콘솔 에러·수치 확인.
9. **배포** — 라이브: https://jinjo202.github.io/pf-dash-a3k9m/longshort/
   저장소 `jinjo202/pf-dash-a3k9m`의 **`longshort/` 하위 폴더에만** 푸시한다 (루트에는 사용자의 다른 대시보드들이 있음 — 절대 건드리지 않는다):
   ```
   git clone --depth 1 https://github.com/jinjo202/pf-dash-a3k9m.git <임시폴더>
   cp index.html data.js backtest_data.js fundamentals.js *.md backtest.py fetch_fundamentals.py update-prices.ps1 <임시폴더>/longshort/
   cd <임시폴더> && git add longshort && git commit -m "롱숏포트 일일 업데이트 YYYY-MM-DD" && git push origin main
   ```
   (일상 업데이트는 data.js만 바뀌므로 data.js + 필요 시 fundamentals.js만 복사해도 됨)
10. **재무 스냅샷 갱신(매일)** — `python fetch_fundamentals.py` → fundamentals.js 재생성 (종목 상세 모달 데이터). 갱신 후 배포 시 fundamentals.js도 함께 복사.

## 원칙

- 가격·NAV 이력은 절대 소급 수정하지 않는다 (오류 발견 시 별도 메모로 정정).
- 아이디어에는 반드시 근거(뉴스/수치)를 포함 — 근거 없는 뷰 금지.
- 스톱 룰은 재량 없이 기계적으로 집행하고 기록한다.
