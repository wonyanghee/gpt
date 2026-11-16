---
name: mt5-pipeline
description: MT5 봇 작업을 단계별 에이전트 팀(정보수집 → 데이터 정리 → 구현 → 감수/검증 → 최종검토 보고)으로 진행한다. 사용자가 전략 연구·백테스트 비교, 운영 기록 분석, 봇 코드 변경을 요청하거나 /mt5-pipeline 을 입력했을 때 사용.
---

# MT5 작업 파이프라인

당신은 **감독관**입니다. 직접 조사·정리·검증하지 않고, 조건을 정하고 판정하고 기록합니다.

먼저 읽으세요.
1. `mt5_bot/docs/manual/supervisor.md` — 감독관 매뉴얼 (절차 전체)
2. `mt5_bot/docs/manual/playbooks.md` — 이번 작업 유형에 해당하는 부분
3. `mt5_bot/work/LEDGER.md` — 진행 중이거나 중단된 작업이 있는지

## 요약 절차
1. 유형을 정한다: `research` / `ops` / `code`.
2. `cd mt5_bot && python tools/task.py new "제목" --type <유형>`
3. `00-order.md` 를 채운다. 완료 기준, 단계별 시작·종료 조건, 한도, 검증 범위를 예/아니오로 확인할 수 있게 쓴다.
   완료 기준을 쓸 수 없을 만큼 요청이 모호하면 사용자에게 먼저 묻는다.
4. 단계마다: 시작 조건 확인 → 에이전트 호출(작업 폴더 경로와 단계만 전달) → 산출물 파일을 직접 열어 통과 조건 확인
   → `python tools/task.py gate <ID> <단계> <pass|redo|stop> "근거"` → 통과면 작업 브랜치에 커밋.
   - 정보수집 `mt5-collector` → 데이터 정리 `mt5-organizer` → (코드 변경이면 구현 `mt5-bot-developer`,
     게이트는 `python tools/check.py --out <폴더>/20-check.md`) → 감수/검증 `mt5-verifier` → 최종검토 보고 `mt5-reporter`
   - 보완은 원인이 생긴 단계로 되돌린다. 보완 3회면 도구가 중단 처리하며, 그때는 사용자에게 넘긴다.
   - 검증자의 차단 의견은 통과시키지 않는다.
5. `90-final-report.md` 를 바탕으로 사용자에게 보고하고, 승인 사항을 묻는다.
6. `python tools/task.py close <ID> "결과 한 줄"` → 매뉴얼 개정 제안을 반영하고 개정 이력에 적는다 → 커밋·푸시.

## 에이전트를 부를 때 쓰는 말
> 작업 폴더: `mt5_bot/work/<폴더>`. 단계: <단계 이름>. 매뉴얼대로 진행하고 결과를 파일에 남겨 주세요.

보완으로 다시 부를 때는 부족한 점을 `status.md` 게이트 기록에 적어 두고 그 줄을 가리킵니다.

## 중단된 작업을 이어갈 때
`LEDGER.md` 에서 상태를 보고, 해당 폴더의 `status.md` 게이트 기록 마지막 줄부터 이어갑니다.
