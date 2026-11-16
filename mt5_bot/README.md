# MT5 나스닥 + 금 자동매매 봇

MetaTrader5 공식 파이썬 API로 **나스닥(US100/NQ)과 금(XAUUSD/GC)**을 매매하는 기본 코드입니다.
같은 전략 코드를 **백테스트 → 드라이런 → 실거래** 순서로 그대로 사용합니다.

> ⚠️ 교육·연구용 기본 코드입니다. 수익을 보장하지 않습니다. 반드시 데모 계좌에서 충분히 검증하고,
> 국내 미등록 해외 브로커 이용 시 법적·출금 위험을 확인하세요.

## 요구사항 정리

| 항목 | 내용 |
|---|---|
| 상품 | CFD(US100, XAUUSD 등) + CME 선물(MNQ/NQ, MGC/GC 등, 자동 롤오버) |
| 실행 환경 | Windows PC/VPS + MT5 터미널 |
| 시간봉 | 15분봉 기본 (상위봉 1시간 필터) |
| 전략 | ① 추세추종: EMA 20/50 교차 + 1시간봉 EMA200 방향 + ADX≥20 <br> ② N봉 박스권 돌파: 직전 20봉 박스 + 박스폭/버퍼/거래량 필터 <br> 종목별로 둘 다 또는 하나만 선택 |
| 청산 | 반대 신호 청산 + **비상 손절 ATR×3** (서버에 SL로 걸어둠) |
| 방향/보유 | 롱·숏 양방향, 오버나잇 허용 |
| 수량 | 종목별 고정 랏/계약 수(기본) 또는 계좌 위험 % 기준 자동 계산 |
| 보호 장치 | 일일 최대손실(기본 3%) 도달 시 그날 신규 진입 중단, 스프레드 필터, 종목당 1포지션, 매매 시간대 제한 |
| 알림/기록 | 텔레그램 + `logs/bot.log` + `logs/trades.csv` |
| 안전장치 | 기본 드라이런. 실거래는 `dry_run: false` + 확인 문구를 넣어야만 실행 |

## 폴더 구조

```
mt5_bot/
├── config.example.yaml   # 설정 예시 (config.yaml 로 복사해서 사용)
├── run_bot.py            # 라이브/드라이런 실행
├── run_backtest.py       # 백테스트 실행
├── run_demo.py           # MT5 없이 돌려보는 데모 (가상 시세)
├── config.demo.yaml      # 데모 전용 설정
├── bot/
│   ├── indicators.py     # EMA, ATR, ADX, 상위봉 정렬(미래참조 방지), 리샘플
│   ├── strategies.py     # 추세추종 / 박스권 돌파 전략
│   ├── broker.py         # MT5Broker(실주문), DryRunBroker(가상체결), 선물 월물 선택
│   ├── engine.py         # 매매 엔진: 신호→청산/진입, 롤오버, 일일손실 한도, 스프레드 필터
│   ├── backtest.py       # 백테스트 엔진 + 통계 + CSV 로더(MT5 내보내기 형식 지원)
│   ├── sizing.py         # 수량 계산 (고정 랏 / 계좌 위험 %)
│   ├── sessions.py       # 매매 시간대 제한
│   ├── sim.py            # 시뮬레이션 브로커 + 가상 시세 생성기 (데모용)
│   ├── notify.py         # 텔레그램 알림, CSV 거래기록
│   └── config.py         # 설정 로딩/검증
└── tests/                # pytest (MT5 없이 실행 가능)
```

## 0단계: 데모 (MT5 없이, 어느 OS에서나)

봇이 어떻게 움직이는지 먼저 보고 싶다면 가상 시세로 돌려볼 수 있습니다. 라이브와 **같은 매매 엔진**이
시뮬레이션 브로커(`bot/sim.py`)에 연결되어 진입·반대 신호 청산·비상 손절·수량 계산·일일 손실 한도가 그대로 동작합니다.

```bash
pip install pandas numpy pyyaml
python run_demo.py                      # 가상 시세 20거래일 재생 (약 30초)
python run_demo.py --speed 0.05         # 봉 하나당 0.05초씩 천천히
python run_demo.py --days 40 --seed 7   # 기간 / 시세 바꾸기
python run_demo.py --html demo.html     # 브라우저로 바로 여는 재생 화면 만들기
python run_demo.py --export demo.json   # 봉·거래·평가금액을 JSON 으로 저장
```

- **`demo.html` 을 더블클릭하면 브라우저에서 바로 재생 화면이 열립니다** (기본 실행 결과가 저장소에 들어 있음. 서버 불필요)
- 설정은 `config.demo.yaml` (잔고 10,000, 거래당 위험 1%). 거래 기록은 `logs/demo_trades.csv`
- **시세는 무작위로 만든 가상 데이터**입니다. 추세 구간과 횡보 구간이 섞여 나오도록 만들었을 뿐 실제 시장과 다르며,
  데모 손익은 전략 성능의 근거가 아닙니다. 성능은 1단계 백테스트에서 실제 과거 데이터로 확인하세요

## 설치 (Windows)

```bat
:: 1) MT5 터미널 설치 후 브로커 계좌(데모 권장) 로그인
:: 2) MT5 > 도구 > 옵션 > 전문가 조언자 > "알고리즘 매매 허용" 체크
:: 3) 파이썬 3.10+ 설치 후
cd mt5_bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.yaml config.yaml
```

## 설정 (`config.yaml`)

1. **종목명 확인**: MT5 "종합시세" 창에서 브로커의 실제 종목명(US100 / NAS100 / USTEC, XAUUSD / GOLD 등)을 `symbol` 에 입력
2. **수량**: 두 가지 방식 중 선택 (`risk.sizing`)
   - `fixed` (기본): 종목별 `lot` 에 적은 고정 랏(선물은 계약 수)
   - `risk_pct`: 비상 손절(ATR×`sl_atr_mult`)에 닿았을 때 손실이 **잔고의 `risk_per_trade_pct` %** 가 되도록 자동 계산
     ```yaml
     risk:
       sizing: risk_pct
       risk_per_trade_pct: 1.0    # 한 번 손절 시 잔고의 1% 손실
     symbols:
       - key: NASDAQ
         max_lot: 2.0             # 수량 상한 (0 = 없음)
     ```
     - 수량 = (잔고 × 위험%) ÷ (1랏 기준 손절 시 손실). 1랏 손실은 MT5 가 계좌 통화로 계산해 줍니다
     - 브로커의 수량 단위로 **내림**하므로 실제 위험은 설정값 이하입니다
     - 최소 수량으로도 한도를 넘으면 **진입하지 않고** 알림을 보냅니다 (소액 계좌 + 선물 1계약에서 흔함)
     - 변동성이 커서 손절 폭이 넓어지면 수량이 줄고, 잔고가 늘면 수량이 늘어납니다
     - 선물 롤오버 재진입은 기존 포지션 수량을 그대로 유지합니다
     - 급등락·갭으로 손절가보다 불리하게 체결되면 실제 손실은 설정값보다 커질 수 있습니다
     - 백테스트는 `backtest.volume_min` / `volume_step` 과 `contract_size` 로 같은 계산을 합니다 (계좌 통화 = 상품 통화 가정)
3. **스프레드 필터**: `max_spread_points` 는 *포인트* 단위 (예: XAUUSD point=0.01 이면 60pt = 0.60달러)
4. **선물**: `type: futures`, `root: MNQ` 처럼 넣으면 만기 `roll_days_before_expiry` 일 이상 남은 가장 가까운 월물을 자동 선택.
   월물이 바뀌면 기존 포지션 청산 → (`roll_reopen: true`) 새 월물로 같은 방향 재진입
5. **전략 선택**: `strategies: [trend, breakout]` — 앞에 있는 전략 신호가 우선. 포지션은 연 전략의 반대 신호로만 청산
6. **매매 시간대**: `sessions` 에 적은 시간에만 신규 진입합니다. 청산·비상손절·롤오버는 시간과 무관하게 동작합니다
   ```yaml
   sessions: ["10:00-12:00", "16:30-23:00"]   # 여러 개 가능, 시작 포함·종료 제외, "22:00-02:00" 자정 넘김 가능
   session_timezone: server                    # server = 브로커 서버 시간(MT5 차트 시간)
   # session_timezone: Asia/Seoul              # 한국 시간 등 IANA 시간대도 가능 (서머타임 자동 반영)
   ```
   - `sessions: []` 이면 제한 없음 (기본값)
   - 백테스트는 `session_timezone: server` 일 때만 시간대 제한을 반영합니다 (봉 시간이 서버 시간이기 때문).
     백테스트와 라이브를 일치시키려면 `server` 를 쓰세요
7. **비밀정보는 환경변수로** (파일에 쓰지 않기)

```bat
set TELEGRAM_BOT_TOKEN=123456:ABC...
set TELEGRAM_CHAT_ID=987654321
:: 선택 (MT5 에 이미 로그인돼 있으면 불필요)
set MT5_LOGIN=12345678
set MT5_PASSWORD=...
set MT5_SERVER=Broker-Demo
```

## 1단계: 백테스트

```bat
:: MT5 에서 과거 15분봉을 받아 바로 테스트 (data\ 에 CSV 저장됨)
python run_backtest.py --symbol NASDAQ --from-mt5 --bars 50000
python run_backtest.py --symbol GOLD   --from-mt5 --bars 50000

:: 저장된 CSV 로 전략별 비교
python run_backtest.py --symbol GOLD --csv data\XAUUSD_M15.csv --strategies trend
python run_backtest.py --symbol GOLD --csv data\XAUUSD_M15.csv --strategies breakout
```

- 결과: 거래수, 승률, 순손익, Profit Factor, 최대낙폭, 전략별 성과 + `backtest_results/*_trades.csv`, `*_equity.csv`
- `symbols[].backtest` 의 `contract_size`(1랏당 가격 1 변동 손익), `spread`, `commission_per_lot` 을 브로커 계약 명세에 맞춰야 금액이 정확합니다
- 체결 가정: 종가 신호 → 다음 봉 시가 체결, 비상손절은 봉 고가/저가로 체크(갭이면 시가). 일일손실 한도·스프레드 필터는 백테스트에 미반영
- 파라미터를 바꿔가며 테스트하되, **기간을 나눠(예: 앞 70% 최적화 / 뒤 30% 검증)** 과최적화를 피하세요

## 2단계: 드라이런 (기본값)

```bat
python run_bot.py --once     :: 한 사이클만 실행해 연결/종목/신호 점검
python run_bot.py            :: 계속 실행 (Ctrl+C 로 종료)
```

- 실제 시세로 신호를 계산하고, 주문은 보내지 않고 `logs/dry_run_state.json` 에 가상 포지션·잔고를 기록합니다 (재시작해도 유지)
- 비상손절, 일일손실 한도, 텔레그램 알림까지 실거래와 같은 흐름으로 동작

## 3단계: 실거래 (데모 계좌부터!)

`config.yaml`:
```yaml
mode:
  dry_run: false
  live_confirm: "I_UNDERSTAND_THE_RISK"
```
- 시작 시 계좌 종류(demo/real)를 로그와 텔레그램으로 알립니다
- 봇이 낸 주문은 `magic` 번호로 구분하므로 수동 매매나 다른 EA 포지션은 건드리지 않습니다
- 서버에서 SL로 청산되면 다음 사이클에 감지해 알림을 보냅니다

## 동작 흐름 (매 `poll_seconds` 초)

1. (드라이런) 가상 포지션 비상손절 체크 / (실거래) 서버측 청산 감지
2. 일일 손익(실현+평가) 확인 → 한도 초과 시 그날 신규 진입 중단 (옵션: 전량 청산)
3. 종목별로: 활성 종목/월물 결정 → 선물 롤오버 → **새 봉이 완성됐을 때만** 전략 신호 계산
   → 반대 신호면 청산 → 포지션이 없으면 매매 시간대·스프레드 확인 후 진입 (SL = 진입가 ∓ ATR×3)

## 테스트

```bash
pip install pandas numpy pyyaml pytest
python -m pytest -q
```
MT5 없이도(리눅스/맥 포함) 전략, 백테스트 체결 로직, 엔진(진입/청산/반전/롤오버/일일한도/스프레드/시간대/수량 계산/서버청산 감지), 드라이런, 설정 검증을 테스트합니다.

## 알아둘 점 / 다음 개선 후보

- 일일 손익의 "하루" 기준은 **브로커 서버 시간** 자정입니다
- 넷팅 계좌(선물 계좌에 흔함)에서는 같은 종목 포지션이 하나로 합쳐지므로 같은 종목을 다른 EA 와 함께 매매하지 마세요
- 개선 후보: 경제지표 발표 시간 회피, 워크포워드 최적화, 나스닥·금 동시 노출 한도
