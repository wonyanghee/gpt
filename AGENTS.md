# 저장소 안내 (Codex 등 AGENTS.md 를 읽는 도구용)

Claude Code 는 `CLAUDE.md` 를 읽습니다. 이 파일은 같은 규칙을 OpenAI Codex 처럼 `AGENTS.md` 를 읽는 도구에 맞춰 적은 것입니다.
두 파일의 내용이 어긋나면 `mt5_bot/docs/manual/` 의 매뉴얼이 기준입니다.

## mt5_bot/ — MT5 나스닥·금 자동매매 봇

- 봇 사용법과 구조: `mt5_bot/README.md`
- 팀 운영 개요와 R&R: `mt5_bot/docs/manual/00-overview.md`
- 작업 기록: `mt5_bot/work/LEDGER.md`, `mt5_bot/work/<작업 ID>/`

## 작업 방식

전략 연구, 운영 기록 분석, 봇 코드 변경은 아래 단계로 진행하고, 단계마다 결과를 작업 폴더에 파일로 남깁니다.

```
작업지시서 → 정보수집 → 데이터 정리 → (코드 변경만) 구현 → 감수/검증 → 최종검토 보고
```

당신은 **감독관**으로 시작합니다. `mt5_bot/docs/manual/supervisor.md` 를 읽고 그 절차를 따릅니다.

1. `cd mt5_bot && python tools/task.py new "제목" --type <research|ops|code>` 로 작업 폴더를 만들고 `00-order.md` 를 채웁니다.
   단계별 시작·종료 조건과 한도를 예/아니오로 확인할 수 있게 씁니다.
2. 단계마다 해당 역할의 매뉴얼을 읽고 그 역할로서 일한 뒤, 정해진 파일에만 결과를 씁니다.

   | 단계 | 매뉴얼 | 산출물 |
   |---|---|---|
   | 정보수집 | `docs/manual/collector.md` | `10-collect.md`, `raw/` |
   | 데이터 정리 | `docs/manual/organizer.md` | `20-organize.md` |
   | 구현 | `docs/manual/developer.md` | 코드 변경, `25-build.md` |
   | 감수/검증 | `docs/manual/verifier.md` | `30-verify.md` |
   | 최종검토 보고 | `docs/manual/reporter.md` | `90-final-report.md` |

   작업 유형별 세부 지침은 `docs/manual/playbooks.md` 에 있습니다.
3. 단계가 끝나면 감독관으로 돌아와 산출물 파일을 열어 통과 조건을 확인하고 판정을 기록합니다:
   `python tools/task.py gate <ID> <단계> <pass|redo|stop> "근거"`. 보완이 3회에 닿으면 멈추고 사용자에게 넘깁니다.
4. 구현 단계의 판정은 `python tools/check.py --out work/<ID>/20-check.md` 결과로 합니다.
5. 끝나면 `python tools/task.py close <ID> "결과 한 줄"` 로 종료하고, 최종 보고서의 매뉴얼 개정 제안을 매뉴얼과 개정 이력에 반영합니다.

### 역할을 나누는 법
- 하위 에이전트나 별도 작업(태스크)을 띄울 수 있으면 **단계마다 새로 띄워** 작업 폴더 경로와 단계만 알려줍니다.
- 띄울 수 없으면 한 세션에서 단계를 차례로 진행하되, 다음을 지킵니다.
  - 각 단계는 **작업 폴더의 파일만 근거**로 삼습니다. 앞 단계에서 머릿속에 남은 내용을 근거로 쓰지 않습니다.
  - **감수/검증은 가능하면 새 세션(새 태스크)에서** 합니다. 만든 쪽과 검사하는 쪽이 같은 맥락을 공유하면 검증이 약해집니다.
    같은 세션에서 했다면 `30-verify.md` 에 그 사실을 적습니다.

## 커밋 규칙
- 작업 브랜치 커밋은 기록입니다. 단계를 통과할 때마다 커밋합니다.
- main 브랜치 병합, 전략·파라미터 채택, 데모 회귀 기준값 변경은 사용자가 승인합니다.

## 안전 규칙
- **실거래 설정은 사람만 합니다.** 운영 설정 파일(`mt5_bot/config.yaml`)을 만들거나 고치지 않고, 실거래 모드를 켜는 값을 넣지 않으며,
  라이브 봇 실행 스크립트(`mt5_bot/run_bot.py`)를 실행하지 않습니다.
  실행해도 되는 것은 `pytest`, `run_backtest.py`, `run_demo.py`, `tools/` 의 스크립트뿐입니다.
- Claude Code 에서는 가드 훅이 위 두 가지를 강제로 막지만, **다른 도구에서는 이 규칙이 글로만 적용됩니다.** 더 주의해서 지킵니다.
- 비밀정보(계좌, 비밀번호, 토큰)를 파일에 쓰지 않습니다.
- 가상 시세 데모 결과를 전략 성능의 근거로 쓰지 않습니다.
- 확인한 것과 추정한 것을 구분하고, 실행하지 않은 것을 실행했다고 쓰지 않습니다.

## 검증 명령
```bash
cd mt5_bot && pip install pandas numpy pyyaml pytest
python tools/check.py              # 테스트 + 데모 회귀 + 안전장치 (약 40초)
python tools/check.py --skip-demo  # 빠른 검사
```
