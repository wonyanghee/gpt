# 정보수집 결과 — 20261116-01

- 수집: 정보수집 담당 / 2026-11-16
- 모드: DEMO (가상 시세). 실거래·드라이런 기록은 다루지 않았다.
- 아래 명령은 모두 `mt5_bot/` 에서 실행했다. `raw/` 는 `work/20261116-01/raw/` 이다.

## 시작 조건 확인
- `mt5_bot/logs/demo_trades.csv` 가 있다 → 충족
  (`ls -la logs` 로 확인. 실행 전 232줄, sha256 `db844c7e…66847464`. 실행 전 상태를 `raw/demo_trades.before_run.csv` 로 복사해 두었다.)

## 수집 항목

수집 순서는 지시서 "주의"에 따라 4 → 1 → 2 → 3 → 5 이다. 항목 1·2·3·5 는 항목 4 실행 뒤 복사한 `raw/demo_trades.csv` 로 집계했다.

### 1. `demo_trades.csv` 의 열 이름, 전체 행 수, `action` 값별 행 수
- 값:
  - 열 이름(13개): `time, mode, key, symbol, action, direction, volume, price, sl, strategy, reason, ticket, profit`
    (파일 맨 앞에 UTF-8 BOM 이 있다. `utf-8-sig` 로 읽었다.)
  - 전체 행 수: 데이터 행 231 (헤더 포함 232줄)
  - `action` 값별 행 수: `open` 116 / `close` 88 / `stop` 27
- 방법: `cd work/20261116-01/raw && python aggregate.py demo_trades.csv | tee aggregate.out.txt`
  (`columns`, `data rows`, `action counts` 줄. 줄 수는 `wc -l`.)
- 원자료: `raw/demo_trades.csv`, `raw/aggregate.py`, `raw/aggregate.out.txt`
- 상태: 수집

### 2. 종목(`symbol`)별 청산 행 수, `profit` > 0 행 수, `profit` 합계
- 값 (청산 행 = `action` 이 `close` 또는 `stop`):

  | symbol | 청산 행 수 | `profit` > 0 행 수 | `profit` 합계 |
  |---|---|---|---|
  | US100 | 62 | 19 | -1202.390800000015389 |
  | XAUUSD | 53 | 17 | -558.6400000001208186 |
  | (전체) | 115 | 36 | -1761.0308000001362076 |

  - 합계는 파일에 적힌 `profit` 문자열을 `Decimal` 로 그대로 더한 값이며 반올림하지 않았다.
  - 참고로 같은 출력에 나온 값: `profit` == 0 인 청산 행은 두 종목 모두 0건, `profit` < 0 은 US100 43건, XAUUSD 36건.
    종목별 `action` 분포는 US100 `close` 47 / `stop` 15 / `open` 63, XAUUSD `close` 41 / `stop` 12 / `open` 53.
- 방법: 항목 1과 같은 명령 (`--- item 2` 아래 줄, `symbol x action` 줄)
- 원자료: `raw/demo_trades.csv`, `raw/aggregate.out.txt`
- 상태: 수집

### 3. 청산 유형(`close` / `stop`)별 행 수, `profit` 합계
- 값:

  | action | 행 수 | `profit` 합계 |
  |---|---|---|
  | close | 88 | 629.9126999998662724 |
  | stop | 27 | -2390.94350000000248 |

  - 합계 방식은 항목 2와 같다(반올림 없음).
- 방법: 항목 1과 같은 명령 (`--- item 3` 아래 줄)
- 원자료: `raw/demo_trades.csv`, `raw/aggregate.out.txt`
- 상태: 수집

### 4. `python run_demo.py --quiet` 출력 전문
- 값: 표준출력 전문 (11줄, 종료 코드 0, 표준오류 출력 없음)

  ```
  === 자동매매 데모 시작: 가상 시세 20거래일, 시작 잔고 10,000 ===
  (가상 데이터입니다. 손익은 전략 성능의 근거가 아닙니다)


  === 데모 결과 ===
  거래수 115건 / 승률 31.3%
  비상손절 27건 / 미청산 포지션 1개
  잔고 10,000.00 → 8,238.97 (평가금액 8,303.51)
    US100: 62건, 손익 -1,202.39
    XAUUSD: 53건, 손익 -558.64
  거래 기록: /home/user/gpt/mt5_bot/logs/demo_trades.csv
  ```
- 방법 (1회 실행, 옵션은 `--quiet` 뿐이라 시드·일수는 기본값):
  ```
  cd /home/user/gpt/mt5_bot && W=work/20261116-01/raw \
   && cp -p logs/demo_trades.csv $W/demo_trades.before_run.csv && date -Is > $W/demo_run.meta.txt \
   && python run_demo.py --quiet > $W/demo_run.stdout.txt 2> $W/demo_run.stderr.txt; \
   echo "exit=$?" >> $W/demo_run.meta.txt; date -Is >> $W/demo_run.meta.txt; cp -p logs/demo_trades.csv $W/demo_trades.csv
  ```
  - 실행 시각: 2026-11-16T08:09:03+00:00 시작, 08:09:32+00:00 종료 (`raw/demo_run.meta.txt`)
  - 실행 뒤 `logs/demo_trades.csv` 와 `raw/demo_trades.csv` 의 sha256 이 같다 (`a7712467…fb5564407`).
- 원자료: `raw/demo_run.stdout.txt`, `raw/demo_run.stderr.txt`(빈 파일), `raw/demo_run.meta.txt`, `raw/demo_trades.csv`
- 상태: 수집

### 5. `time` 열 값 범위와 데모 출력의 시뮬레이션 날짜 범위
- 값:
  - `time` 열 최소: `2026-11-16T08:09:03` / 최대: `2026-11-16T08:09:32` (서로 다른 값 30개, 초 단위)
  - 이 범위는 항목 4의 데모 실행 시작·종료 시각(08:09:03 ~ 08:09:32)과 같다.
  - 데모 출력의 시뮬레이션 날짜 범위: **출력에 없음.** `--quiet` 출력 전문(항목 4)에 날짜는 한 군데도 나오지 않으며,
    기간에 관한 표기는 "가상 시세 20거래일" 뿐이다.
- 방법: 항목 1과 같은 명령 (`--- item 5` 아래 줄), `raw/demo_run.stdout.txt` 전문 확인
- 원자료: `raw/aggregate.out.txt`, `raw/demo_run.stdout.txt`, `raw/demo_run.meta.txt`
- 상태: `time` 범위는 수집 / 시뮬레이션 날짜 범위는 **미수집** (사유: 허용 출처인 `--quiet` 출력에 날짜가 없다.
  `--quiet` 없이 다시 실행하면 나올 수 있으나 데모 실행 한도 1회를 이미 썼고, 코드·`--export` 결과는 범위 밖이라 확인하지 않았다.)

## 한도 사용
- 데모 실행 1회 / 최대 1회
- 그 밖의 명령: 읽기·복사·집계용만 (`ls`, `wc`, `head`, `sha256sum`, `cp` → `raw/`, `diff`, `grep`, `raw/aggregate.py`)
- 웹·백테스트: 사용하지 않음

## 종료 사유
- 필수 항목 5개를 모두 처리. 항목 1~4 수집, 항목 5 는 절반(시뮬레이션 날짜 범위) 미수집 1건.

## 감독관에게
- **지시서 항목 5**: `--quiet` 출력에는 시뮬레이션 날짜가 없어 허용 출처만으로는 채울 수 없었다. 필요하면 출처(예: `--quiet` 없는 출력, `--export` JSON, 코드)나 실행 한도를 지시서에서 바꿔야 한다.
- **`time` 열**: 값이 실행한 시점의 벽시계 시각이다(범위가 실행 시작·종료 시각과 같음). 가상 시세의 봉 시각을 담은 열은 파일에 없다.
- **빈 칸** (`raw/aggregate.out.txt` 의 `empty cells` 줄): `key` 열은 231행 중 115행이 비어 있고(`close`/`stop` 행 전부. `open` 행에는 `GOLD`/`NASDAQ` 가 들어 있음), `profit` 열은 `open` 116행이 비어 있다.
- **`open` 116 대 청산 115**: 차이 1건. 데모 출력에는 "미청산 포지션 1개"가 있다. 파일 마지막 행은 `ticket` 116 의 US100 `open` 이다.
- **데모 출력의 다른 수치**: 승률 31.3%, 잔고 10,000.00 → 8,238.97, 평가금액 8,303.51 이 출력에 있다. 지시서의 대조 항목(거래수, 비상손절 건수, 종목별 건수·손익)에는 없는 수치라 대조용 값은 따로 모으지 않았다.
- **실행 전 파일과의 비교**: `raw/demo_trades.before_run.csv`(실행 전 사본)와 `raw/demo_trades.csv` 는 `time` 열을 뺀 나머지가 모두 같다
  (`diff <(cut -d, -f2- demo_trades.csv) <(cut -d, -f2- demo_trades.before_run.csv)` 출력 없음). 실행 전 사본의 집계는 `raw/aggregate.before_run.out.txt` 에 있다. 지시서가 요구한 항목은 아니다.
- **범위 관련 고지**: 실행 옵션과 기록 파일 경로를 확인하려고 `run_demo.py` 에서 `add_argument`·`demo_trades` 가 들어간 줄만 `grep` 으로 보았다(63~69, 94행). 수치 수집에는 쓰지 않았다.
- `profit` 값은 부동소수 표기 그대로 기록되어 있다(예: `189.27999999999338`). 반올림은 정리 단계 몫으로 남겼다.
- `logs/` 는 `.gitignore` 대상이라 `logs/demo_trades.csv` 변경은 git 상태에 나타나지 않는다. 저장소에서 새로 생긴 것은 `work/20261116-01/` 아래 파일뿐이다. 커밋은 하지 않았다.
