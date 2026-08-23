Task 5 Report: Photos and Analytics Pages

Date: 2026-08-23
Worktree: /Users/gimhyeongseog/Desktop/watersports-agent/.worktrees/surfirst-admin-redesign

Summary
- Reshaped `/photos/admin` into a delivery-focused page with the required `photo-delivery`, `album-create-panel`, and `list` regions.
- Reshaped `/dashboard/` into an analytics report wrapper with the required `analytics-report`, `p-ov`, `p-ch`, and `p-cal` regions.
- Preserved the existing photo APIs, analytics API, album actions, Chart.js usage, and dashboard rendering functions.

TDD Record
1. Added `test_photos_page_has_delivery_regions` and `test_dashboard_page_has_report_regions` to `tests/test_admin_ui_assets.py`.
2. Ran:
   `/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py::test_photos_page_has_delivery_regions tests/test_admin_ui_assets.py::test_dashboard_page_has_report_regions -v`
3. Confirmed both tests failed first on missing region markers.
4. Implemented the markup and selector changes.
5. Re-ran the same targeted tests and confirmed both passed.

Implementation Details

Photos (`app/routers/photos.py`)
- Added the `#photo-delivery` wrapper and page heading copy: `앨범을 만들고 QR을 손님에게 보여주세요.`
- Added the `#album-create-panel` section using the shared admin shell classes.
- Kept `id="list"` as the album list mount point.
- Reshaped album rendering into delivery cards with:
  - QR image
  - album code and meta
  - delete action
  - share link
  - `aria-live="polite"` upload status region per album
  - existing drop zone, file input, and thumbs mount
- Preserved `createAlbum()`, `load()`, `loadThumbs()`, `deleteAlbum()`, `deletePhoto()`, `bindDrops()`, and `uploadFiles()` behavior, with only markup/class changes and upload status messaging added.
- Upload status now reports:
  - `<n>장 업로드 중...`
  - `업로드 완료`
  - `업로드 실패. 다시 시도해 주세요.`

Dashboard (`app/routers/dashboard.py`)
- Added the `#analytics-report` wrapper and page heading copy: `영업 리포트`
- Kept `id="p-ov"`, `id="p-ch"`, and `id="p-cal"` unchanged.
- Replaced the old tab button markup with `.report-tabs` and `.report-tab`.
- Updated `sw(tab)` to clear and set `.report-tab` instead of `.tab`.
- Left the existing chart containers, analytics fetch flow, Chart.js usage, and report render functions intact.

Shared CSS (`static/admin/surf-admin.css`)
- Added page-level styles for:
  - album create panel
  - album list and album cards
  - QR tile, meta, share link, and upload status
  - drag-and-drop region
  - analytics report tabs
  - shared card surface treatment for `.cbox` and `.cal-wrap`
- Ensured buttons and tap targets remain at least 40px high where required.

Tests
- Focused red/green check:
  - `/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py::test_photos_page_has_delivery_regions tests/test_admin_ui_assets.py::test_dashboard_page_has_report_regions -v`
  - Result: passed after implementation
- Full requested regression set:
  - `/Users/gimhyeongseog/Desktop/watersports-agent/venv/bin/python -m pytest tests/test_admin_ui_assets.py tests/test_photo_cleanup.py tests/test_landing.py -v`
  - Result: 32 passed

Notes / Concerns
- `uploadFiles()` now surfaces success and error text through the live region, but a successful upload still refreshes the list immediately via `load()`. That preserves the prior behavior while exposing status before the refresh.
- Existing inline legacy styles in the route HTML were left in place unless the task required a structural or class change. Shared visual additions were added in `surf-admin.css`.
