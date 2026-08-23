# Task 3 Report: Home Operations Console

## Scope

Implemented the `/admin/` home operations console in the feature worktree only.

Touched files:

- `app/routers/admin.py`
- `static/admin/surf-admin.css`
- `tests/test_admin_ui_assets.py`

Did not edit:

- `static/landing/index.html`
- availability route behavior
- photos route behavior
- dashboard route behavior

## TDD record

### Red

Added `test_admin_home_has_operations_console_regions` to `tests/test_admin_ui_assets.py` and ran:

```bash
/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py::test_admin_home_has_operations_console_regions -v
```

Observed expected failure on missing `id="ops-alerts"` in `/admin/`.

### Green

Reworked the admin home HTML/JS and shared CSS, then reran:

```bash
/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py::test_admin_home_has_operations_console_regions -v
```

Result: pass.

## Implementation summary

### `app/routers/admin.py`

- Replaced the old home-only cards/chart content under `/admin/` with the operations console layout.
- Added the required home regions and copy:
  - `id="ops-alerts"`
  - `id="today-timeline"`
  - `id="intents"`
  - `id="convos"`
  - visible `오늘 운영`
  - visible `예약 추가`
- Kept existing admin APIs unchanged:
  - `api/stats`
  - `api/intents`
  - `api/conversations`
  - `api/reservation-stats`
  - `api/reservations`
- Kept existing `openUser`, edit, memo, delete, and modal flows.
- Extended `openCard()` with an `intents` case so the new alert and metric open a detail modal instead of dropping behavior.
- Preserved `pending` and `revenue` modal cases and kept them reachable from the new metric buttons.
- Added today timeline rendering from reservation `slot_date` and `time_slot`.
- Used a KST client-side date key only for display-side filtering of the timeline, while still preferring server reservation date fields (`slot_date`) for the actual comparison.
- Added guards around chart rendering so removal of the old home chart canvases does not break theme toggle or page refresh logic.

### `static/admin/surf-admin.css`

- Added shared home-console styles for:
  - operations layout grid
  - alert list/cards
  - timeline rows
  - clickable metric presentation
  - responsive single-column collapse under `920px`

### `tests/test_admin_ui_assets.py`

- Added the home structure test required by the brief.

## Verification

Ran exactly:

```bash
/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py tests/test_login_bruteforce.py -v
```

Result: `23 passed`.

## Concerns / notes

- The timeline filter uses reservation `slot_date` values and compares them to a KST-formatted client-side date key. That keeps the display aligned with the existing Korea-based backend data without changing API contracts.
- The old chart helpers remain in `admin.py` but are now effectively dormant on the home page. I only added guards to keep existing theme-refresh behavior from throwing when chart canvases are absent.

## Review fix round 1 (2026-08-23)

### Findings addressed

1. Tightened timeline status styling so known statuses are explicit:
   - `예약` -> `sf-status--ok`
   - `입금대기` -> `sf-status--pending`
   - `노쇼` -> `sf-status--danger`
   - `취소` / `예약취소` / `취소됨` -> `sf-status--muted`
   - unknown values -> `sf-status--muted`
2. Aligned the `오늘 방문` metric action with its label by changing it from `openCard('confirmed')` to a dedicated `openCard('today-reservations')` case.
3. Adjusted the timeline empty-state copy from `오늘 입력된 예약이 없습니다.` to `오늘 예약이 없습니다.`

### Files changed in round 1

- `app/routers/admin.py`
- `tests/test_admin_ui_assets.py`

### TDD record for round 1

Added targeted tests:

- `test_admin_home_today_metric_targets_today_reservations_modal`
- `test_admin_home_timeline_uses_explicit_status_mapping`

Verified red with:

```bash
/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py -k "today_metric_targets_today_reservations_modal or timeline_uses_explicit_status_mapping" -v
```

Observed both tests fail against the previous implementation.

Applied the inline `DASHBOARD_HTML` fix in `app/routers/admin.py`, then reran the targeted command and got both tests passing.

### Verification for round 1

Ran:

```bash
/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py tests/test_login_bruteforce.py -v
```

Result: `25 passed`.
