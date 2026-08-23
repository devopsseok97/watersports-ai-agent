# Task 2 Report: Login and Shared Shell Adoption

## Status

Completed on August 23, 2026 in worktree `/Users/gimhyeongseog/Desktop/watersports-agent/.worktrees/surfirst-admin-redesign`.

## Scope Delivered

- Applied shared admin assets to authenticated admin pages:
  - `app/routers/admin.py`
  - `app/routers/availability.py`
  - `app/routers/photos.py`
  - `app/routers/dashboard.py`
- Added the shared shell with exact nav labels:
  - `홈`
  - `예약`
  - `사진`
  - `분석`
- Updated login to use `surf-admin.css` and the Surfirst console copy.
- Added login-specific styles to `static/admin/surf-admin.css`.
- Extended `tests/test_admin_ui_assets.py` with authenticated HTML assertions using the required route-module `verify_session` monkeypatch targets.

## TDD Notes

1. Added failing tests first in `tests/test_admin_ui_assets.py`.
2. Verified red state with:

   `/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py -v`

3. Implemented shared shell and login changes.
4. Re-ran the requested coverage command and reached green.

## Implementation Notes

- Login now references `/static/admin/surf-admin.css` and uses the shared token classes:
  - `sf-login`
  - `sf-login-card`
  - `sf-login-form`
  - `sf-check`
- Authenticated admin pages now include:
  - `<link rel="stylesheet" href="/static/admin/surf-admin.css">`
  - `<script src="/static/admin/surf-admin.js"></script>`
- Shared shell adoption was done without renaming page-specific data IDs used by later tasks.
- Theme initialization now comes from `SurfAdmin.initTheme('themebtn')`.
- Pages that need a repaint after theme change keep that behavior by attaching a post-toggle listener after shared theme initialization.
- The auth test ruling was followed by patching imported route-module names instead of `app.services.auth.verify_session`.

## Verification

Ran:

`/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py tests/test_login_bruteforce.py -v`

Result:

- 21 tests passed
- 0 failures

## Warnings / Concerns

- Pytest emitted existing dependency deprecation warnings from Pydantic, Supabase auth, and per-request cookies in `httpx`. No new functional failures were introduced by Task 2.
- Page-specific inline CSS is still present where later tasks will continue reshaping content. Task 2 limited itself to shell adoption and login integration.

## Files Changed

- `app/routers/admin.py`
- `app/routers/availability.py`
- `app/routers/photos.py`
- `app/routers/dashboard.py`
- `static/admin/surf-admin.css`
- `tests/test_admin_ui_assets.py`
