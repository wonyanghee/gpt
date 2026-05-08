# SSENSE Archive Minimalist – E2E Scenario Matrix

## Scope
This document defines manual/automatable E2E scenarios for the standalone HTML demo and the Next.js catalog page.

Targets:
- `index.html`
- `src/app/page.tsx`

## Scenario 1: Tab click flow (ALL → TOPS → PANTS)

| Step | Action | Expected Result |
|---|---|---|
| 1 | Load page | Default tab is `ALL`, 4 items shown |
| 2 | Click `TOPS` | Only `Ripstop Utility Vest` remains, count is 1 |
| 3 | Click `PANTS` | Only `Panel Cargo Trouser` remains, count is 1 |

## Scenario 2: Search typing flow (`u` → `ut` → `utility`)

Precondition: tab is `ALL`.

| Step | Action | Expected Result |
|---|---|---|
| 1 | Type `u` in search box | 3 items visible |
| 2 | Continue to `ut` | 2 items visible |
| 3 | Continue to `utility` | 1 item visible: `Ripstop Utility Vest` |

## Scenario 3: A/B mode toggle flow

| Step | Action | Expected Result |
|---|---|---|
| 1 | Verify initial mode | Mode A active by default |
| 2 | Click mode `B` | UI switches to structural-emphasis variant (stronger borders/tab underline) |
| 3 | Click mode `A` | UI reverts to baseline minimalist style |

## Scenario 4: Compound filter behavior

| Step | Action | Expected Result |
|---|---|---|
| 1 | Select `OUTERWEAR` tab | 2 items visible |
| 2 | Type `field` | 1 item visible: `Softshell Field Parka` |
| 3 | Clear search input | Returns to 2 visible outerwear items |

## Scenario 5: Responsive layout behavior

| Viewport | Expected Layout |
|---|---|
| > 1024px | Sidebar + 4-column product grid |
| <= 1024px | Stacked layout + 2-column grid |

## Automation Notes
- This matrix can be translated into Playwright tests by querying:
  - tab buttons by text (`ALL`, `TOPS`, etc.)
  - search input by placeholder (`Search artifacts`)
  - result count label (`N ITEMS`)
- For style-mode checks, assert `body` class toggles (`mode-b` present/absent).
