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

## Fix Round 1

### Review Finding Addressed

Blocked review item: minimum 40px touch targets were not consistently met on page-specific controls.

Fixed:

- `app/routers/availability.py`
  - reservation row action buttons now keep `min-width:40px` and `min-height:40px`, including the mobile override
- `app/routers/dashboard.py`
  - calendar nav buttons now use `40x40`
  - tab buttons now declare `min-width:40px` and `min-height:40px`
- `app/routers/photos.py`
  - photo thumbnail delete buttons now use `40x40` with matching `line-height:40px`
- `tests/test_admin_ui_assets.py`
  - added a static regression test that asserts the generated HTML/CSS strings retain those 40px floors on the known selectors

### Command

`/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py tests/test_login_bruteforce.py -v`

### Output

```text
collected 22 items

tests/test_admin_ui_assets.py::test_shared_admin_css_served PASSED
tests/test_admin_ui_assets.py::test_shared_admin_js_served PASSED
tests/test_admin_ui_assets.py::test_shared_admin_theme_contract PASSED
tests/test_admin_ui_assets.py::test_landing_does_not_reference_admin_assets PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_reference_shared_assets[/admin/] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_reference_shared_assets[/availability/admin] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_reference_shared_assets[/photos/admin] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_reference_shared_assets[/dashboard/] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_share_nav_labels[/admin/] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_share_nav_labels[/availability/admin] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_share_nav_labels[/photos/admin] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_share_nav_labels[/dashboard/] PASSED
tests/test_admin_ui_assets.py::test_login_page_uses_surfirst_console_copy PASSED
tests/test_admin_ui_assets.py::test_touch_targets_keep_40px_minimums PASSED
tests/test_login_bruteforce.py::test_repeated_wrong_password_gets_locked[/admin/login] PASSED
tests/test_login_bruteforce.py::test_repeated_wrong_password_gets_locked[/ops/login] PASSED
tests/test_login_bruteforce.py::test_lock_blocks_even_correct_password[/admin/login-correct-horse] PASSED
tests/test_login_bruteforce.py::test_lock_blocks_even_correct_password[/ops/login-ops-secret] PASSED
tests/test_login_bruteforce.py::test_success_clears_failure_count[/admin/login-correct-horse] PASSED
tests/test_login_bruteforce.py::test_success_clears_failure_count[/ops/login-ops-secret] PASSED
tests/test_login_bruteforce.py::test_admin_lock_does_not_lock_ops PASSED
tests/test_login_bruteforce.py::test_ip_rotation_hits_global_cap PASSED

22 passed, 10 warnings in 1.72s
```

## Fix Round 2

### Review Finding Addressed

Remaining touch-target gaps from re-review:

- `app/routers/dashboard.py`
  - `.ibtn` now uses `40x40`
  - `.rbtn` now declares `min-width:40px` and `min-height:40px`
- `app/routers/photos.py`
  - `.delbtn` now declares `min-width:40px` and `min-height:40px` on desktop as well
- `tests/test_admin_ui_assets.py`
  - extended `test_touch_targets_keep_40px_minimums` to cover `.ibtn`, `.rbtn`, and `.delbtn`

### Command

`/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py tests/test_login_bruteforce.py -v`

### Output

```text
collected 22 items

tests/test_admin_ui_assets.py::test_shared_admin_css_served PASSED
tests/test_admin_ui_assets.py::test_shared_admin_js_served PASSED
tests/test_admin_ui_assets.py::test_shared_admin_theme_contract PASSED
tests/test_admin_ui_assets.py::test_landing_does_not_reference_admin_assets PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_reference_shared_assets[/admin/] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_reference_shared_assets[/availability/admin] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_reference_shared_assets[/photos/admin] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_reference_shared_assets[/dashboard/] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_share_nav_labels[/admin/] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_share_nav_labels[/availability/admin] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_share_nav_labels[/photos/admin] PASSED
tests/test_admin_ui_assets.py::test_authenticated_admin_pages_share_nav_labels[/dashboard/] PASSED
tests/test_admin_ui_assets.py::test_login_page_uses_surfirst_console_copy PASSED
tests/test_admin_ui_assets.py::test_touch_targets_keep_40px_minimums PASSED
tests/test_login_bruteforce.py::test_repeated_wrong_password_gets_locked[/admin/login] PASSED
tests/test_login_bruteforce.py::test_repeated_wrong_password_gets_locked[/ops/login] PASSED
tests/test_login_bruteforce.py::test_lock_blocks_even_correct_password[/admin/login-correct-horse] PASSED
tests/test_login_bruteforce.py::test_lock_blocks_even_correct_password[/ops/login-ops-secret] PASSED
tests/test_login_bruteforce.py::test_success_clears_failure_count[/admin/login-correct-horse] PASSED
tests/test_login_bruteforce.py::test_success_clears_failure_count[/ops/login-ops-secret] PASSED
tests/test_login_bruteforce.py::test_admin_lock_does_not_lock_ops PASSED
tests/test_login_bruteforce.py::test_ip_rotation_hits_global_cap PASSED

22 passed, 10 warnings in 2.07s
```
