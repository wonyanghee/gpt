# 저장소 안내

## mt5_bot/ — MT5 나스닥·금 자동매매 봇

사용법과 구조는 `mt5_bot/README.md`, 에이전트 팀 설명은 `mt5_bot/docs/agent-team.md` 에 있습니다.

### 작업 절차 (총괄 = 메인 세션)
코드 변경 요청은 서브에이전트에게 나눠 맡기고 아래 순서로 진행합니다.

1. `mt5-bot-developer` 가 구현하고 테스트를 작성한다.
2. `mt5-test-engineer` 가 pytest 와 데모 회귀를 확인한다.
3. 아래 파일이 바뀌었으면 `mt5-risk-reviewer` 가 검토한다. **차단** 판정이면 개발자에게 되돌린다.
   `engine.py`, `broker.py`, `sizing.py`, `sessions.py`, `strategies.py`, `config.py`, `backtest.py`, `run_bot.py`
4. 결과를 사용자에게 보고한다. **커밋과 푸시는 사용자가 승인한 뒤에** 한다.

- 전략·백테스트·파라미터 질문은 `mt5-strategy-researcher` 에게 맡긴다. 연구원은 제안만 하고, 적용 여부는 사용자가 정한다.
- 로그·거래 기록 분석은 `mt5-ops-analyst` 에게 맡긴다. 보고서는 `mt5_bot/reports/` 에 저장된다.
- 오타 수정처럼 동작이 바뀌지 않는 작은 변경은 총괄이 직접 해도 된다.

### 안전 규칙
- 실거래 설정은 사람만 한다. `mt5_bot/config.yaml` 을 만들거나 고치지 않고, `dry_run: false` 나 실거래 확인 문구를
  넣지 않으며, `run_bot.py` 를 실행하지 않는다. 실행해도 되는 것은 `pytest`, `run_backtest.py`, `run_demo.py` 뿐이다.
- `.claude/hooks/mt5_guard.py` 가 위 두 가지(운영 설정 수정, `run_bot.py` 실행)를 도구 호출 단계에서 막는다.
- 비밀정보(계좌, 비밀번호, 토큰)를 파일에 쓰지 않는다.
- 가상 시세 데모 결과를 전략 성능의 근거로 쓰지 않는다.

### 검증 명령
```bash
cd mt5_bot && python -m pytest -q        # 테스트
cd mt5_bot && python run_demo.py --quiet # 데모 회귀 (기본 시드 기준: 거래 115건, 비상손절 27건)
```
