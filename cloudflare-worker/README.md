# 배당주 조회 서버 (Cloudflare Worker)

정적 사이트(github.io)에서 **유니버스 밖 종목**을 검색해도 유니버스 종목과 똑같이
(시세·배당수익률·PER/PBR·시가총액·캔들+MA/RSI·분기/연간 실적·배당일정) 나오게 하는
무료 백엔드다.

> 왜 필요한가: 브라우저에서 야후 파이낸스를 직접 부르면 **CORS**로 막힌다. 이 Worker가
> 서버사이드에서 야후(+한글명은 네이버)로 조회해, 로컬 `serve.py`의 `/div-lookup`과
> **똑같은 JSON**을 CORS 허용 헤더로 돌려준다. (로컬 `python serve.py` 사용 시엔 불필요.)

무료 플랜: **하루 10만 요청** — 개인용으로 차고 넘친다. 카드 등록 불필요.

---

## 배포 (약 5분, 한 번만)

### 방법 A — 대시보드 붙여넣기 (가장 쉬움)
1. https://dash.cloudflare.com 가입/로그인 (무료).
2. 왼쪽 **Workers & Pages** → **Create application** → **Create Worker**.
3. 이름 지정(예: `dividends-lookup`) → **Deploy** (기본 hello-world로 일단 배포됨).
4. **Edit code** → 편집기 내용을 **전부 지우고** 이 폴더의 [`worker.js`](worker.js) 내용을 붙여넣기 → **Deploy**.
5. 상단에 뜨는 URL 복사: `https://dividends-lookup.<your-subdomain>.workers.dev`

### 방법 B — Wrangler CLI
```bash
npm i -g wrangler
wrangler login
cd cloudflare-worker
wrangler deploy worker.js --name dividends-lookup
# 출력된 https://dividends-lookup.<subdomain>.workers.dev 복사
```

---

## 연결
배당주 탭 → 검색창 아래 **⚙ 유니버스 밖 조회 설정** 펼치기 → Worker URL 붙여넣고 **저장**.
(브라우저 localStorage에만 저장 — 기기마다 한 번씩.)

이후 검색창에 종목명·티커·6자리코드 입력하고 **Enter**(또는 🔎 직접 조회) → 실시간 조회.

## 확인
```bash
curl "https://dividends-lookup.<subdomain>.workers.dev/?q=AAPL"
# {"ok":true,"yf":"AAPL","n":"Apple Inc.","q":{"price":...,"per":...,"fin":{...}}}
```

---

## 동작
- 심볼 해석: 6자리→KR(코스피/코스닥 자동), 한글명→네이버 자동완성, 영문명·티커→야후 검색
- 데이터: 야후 `chart`(시세·OHLC·배당) + `quoteSummary`(PER·PBR·시총·성향, **crumb 인증**) +
  `fundamentals-timeseries`(매출·영업이익·순이익)
- 반환 JSON은 `serve.py`의 `/div-lookup`과 동일 스키마 → 프런트 수정 불필요

## 주의
- 공개 종목 시세만 조회한다(민감정보 없음). 그래도 URL 노출이 싫으면 Worker에
  간단한 토큰 체크를 추가하거나, 로컬 `serve.py`만 쓰면 된다.
- 야후 비공식 API라 스키마가 바뀌면 조정이 필요할 수 있다.
