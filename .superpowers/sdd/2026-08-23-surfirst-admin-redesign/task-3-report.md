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
