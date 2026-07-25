# AGFDATA - Furniture Data Management System

## Original Problem Statement
Aplikasi rekap data barang furniture "AGFDATA" - Database Barang, PO, Barang Masuk, Staffing, SPK, Progres Barang, Rekap Data dengan 3 role (admin/staff/tamu), mobile responsive.

## Architecture
- Backend: FastAPI + MongoDB (Motor) + JWT httpOnly cookies (~1620 lines)
- Frontend: React + shadcn/ui + Tailwind CSS
- Storage: Emergent Object Storage
- Exports: ReportLab (PDF + images), xlsxwriter (Excel + embedded images), XLSX.js (CSV)

## Test Credentials
- Admin: admin@agfdata.com / admin123
- Staff: staff@agfdata.com / staff123
- Tamu: tamu@agfdata.com / tamu123

## Implementation Log

### Iteration 11 (Feb 2026) - Activity Log / Audit Trail
- **New Activity Log menu** (admin only) at `/activity-log` — table showing riwayat login, create, update, delete di semua menu dengan filter (action / resource / user / tanggal)
- **Middleware auto-logging**: FastAPI middleware intercepts all successful mutations on `/api/*` (POST/PUT/DELETE/PATCH) and inserts `{user_id, user_email, user_role, action, resource, resource_label, resource_id, path, method, status_code, timestamp, ip}` — no per-endpoint instrumentation needed
- **Explicit login/logout logging**: `/api/auth/login` logs success + failure (with attempted email); `/api/auth/logout` logs before clearing cookie
- **Endpoints** (declared before `app.include_router`): `GET /api/activity-log?action=&resource=&user_id=&date_from=&date_to=&limit=` (admin only, max 2000), `DELETE /api/activity-log/purge?before=YYYY-MM-DD` (admin only)
- **Indexes**: `timestamp` DESC, `user_id`, `resource` for fast filtering
- Sidebar navigation includes new "Activity Log" item (admin role only)
- Verified via curl: GET returns entries sorted desc, purge with missing `before` → 400, guest → 403

### Iteration 10 (Feb 2026) - Komplit Notifications + Progres Edit + Rekap Sync + Legacy Rebalance
- **BarangMasuk KOMPLIT badge**: card shows "KOMPLIT PO" when `sum(qty_diterima) >= sum(qty)` across all PO items; per-item "KOMPLIT" badge when `qty_diterima >= qty`; qty label now shows `X / total_po` for clarity
- **Staffing KOMPLIT TERKIRIM badge**: card shows badge when `sum(qty_staffed) >= sum(qty)` across PO; per-item KOMPLIT + `X / total_po` label
- **Progres Barang edit entry**: new `PUT /api/progres/{entry_id}` with pipeline validation excluding self (`sums - own_old_qty`); frontend Edit button per entry in history panel; dialog title switches to "Edit Entry Progres"
- **Progres PDF export**: now aggregates stage entries via `$group`, includes **Tanggal** column, `tanggal` filter shows entries dated on that day only
- **Rekap Progres sync**: `/api/rekap/progres` rebuilt to aggregate from stage entries (previously read from legacy cumulative docs → showed zeros). Returns `sisa_grinda/servis/finishing/packing` + `tanggal_terakhir`. Frontend table shows Tanggal + sisa row-under-value per stage; Excel/CSV export includes all sisa columns
- **Legacy rebalance on startup**: idempotent script that walks each PO+barang, detects downstream > upstream inconsistencies, and reduces qty of most-recent entries at excess stages until sums are pipeline-consistent. Ran once and fixed 41 groups.

### Iteration 9 (Feb 2026) - Progres Barang stage-entry model + backlog cleanup
- **PROGRES BARANG rebuilt** as per-date, per-stage entry log (each POST creates a new record, no more upsert):
  - `POST /api/progres` accepts `{po_id, item_id, stage, qty, tanggal, ...meta}`; validates pipeline: grinda ≤ (qty_masuk − grinda_sum); servis ≤ (grinda_sum − servis_sum); finishing ≤ (servis_sum − finishing_sum); packing ≤ (finishing_sum − packing_sum); returns HTTP 400 with descriptive Indonesian error including current sisa
  - Response includes `sisa_setelah_input` and `upstream_label` for UX
  - `GET /api/progres/entries?po_id=&item_id=` returns entry history (sorted tanggal desc)
  - `DELETE /api/progres/{id}` removes an entry (admin only)
  - `GET /api/progres/by-po` now aggregates via `$group` per stage + returns `sisa_grinda`/`sisa_servis`/`sisa_finishing`/`sisa_packing`
- **Migration on startup**: converted 27 legacy cumulative progres docs into stage entries (1–4 entries each, backdated to updated_at)
- **Frontend**: `Tambah Progres` dialog now has Stage select + live sisa hint + qty cap by upstream sisa. Item cards show 4 stat tiles (per stage: value + sisa). Toggle "Lihat Riwayat Entry" per barang shows the full entry log with delete option.
- **Backlog knocked out:**
  - `SPKItem` Pydantic model added (SPKCreate.items now `List[SPKItem]` — barang_id, nama_barang, qty (ge=1), pengrajin_list default_factory=list, catatan, harga, etc.)
  - MongoDB `$group` aggregation for `_get_packing_map`, `_get_stage_sums`, `_get_qty_masuk` — no more O(N) collection scans
  - `DialogDescription` added to all `DialogContent` (BarangMasuk, DatabaseBarang, POPage, SPKPage, Staffing, UserManagement, ProgresBarang) — a11y warnings fixed
  - Verified `update_bm` already uses validate-first (iter6 fix intact)

### Iteration 8 (Feb 2026) - Progres Barang Input Dialog + Tanggal
- **New "Tambah Progres" dialog** on Progres Barang page with source toggle: Dari PO (cascading dropdown PO → Barang, auto-fills metadata) or Manual (barang from full DB, editable overrides)
- **Tanggal field** (`tanggal: Optional[str]`) added to `ProgresUpdate` model; defaults to today UTC; saved in progres doc; returned in `/api/progres/by-po`; shown as badge with calendar icon on each item card
- **All 4 stages (grinda/servis/finishing/packing) capped by qty_masuk** on the server when linked to a PO (previously only packing). Manual mode (no po_id) persists stage values as-entered — no silent zeroing
- **Existing inline table + edit preserved** (per user request "tabel sudah sesuai dan pertahankan")
- Tests: 16/16 backend pass (test_iter8.py) + full frontend flow verified

### Iteration 7 (Feb 2026) - Staffing-by-Ready + PO Totals + SPK Pengrajin/Note + Multi-Pengrajin Barang
- **Staffing dilimit oleh qty_ready (packing dari Progres)**: `/api/po*` now returns `qty_ready` per item (sum of `progres.packing`). `create_staffing` & `update_staffing` cap qty by `min(qty_po - staffed, qty_ready - staffed)` and return HTTP 400 with `Ready: X ... sisa: Y`. Frontend Staffing dialog shows Ready label + caps input.
- **PO subtotal + grand total**: UI shows `qty × harga_jual` per item and Grand Total per PO card. Detail modal shows itemized subtotal + Grand Total banner. PDF export table now has Harga Jual + Subtotal columns + Grand Total row.
- **SPK per-item pengrajin dropdown + note**: If barang has `pengrajin_list`, SPK dialog shows Select dropdown with primary + all alternates; else plain Input. Added per-item `catatan` field displayed in card & detail with 📝 prefix.
- **Database Barang multi-pengrajin**: Added `pengrajin_list: List[str]` to BarangCreate. Dialog has "Pengrajin Tambahan" section with Add/Remove UI. Card badge shows "+N lainnya". Guest role hides both `nama_pengrajin` and `pengrajin_list`.
- Tests: 15/15 backend pass (test_iter7.py) + all 4 frontend features verified

### Iteration 6 (Feb 2026) - Data Integrity + Validation Hardening
- **BUG FIX**: `update_po` now preserves cumulative `qty_staffed` and `qty_diterima` per barang_id (was resetting to 0 on edit)
- **Pydantic models**: added `BarangMasukItem` & `StaffingItem` (Field ge=0, barang_id required) - replaces raw `List[Dict[str, Any]]`
- **Backend validation**: `create/update_barang_masuk` and `create/update_staffing` reject qty > sisa PO with descriptive Indonesian error (HTTP 400)
- **Validation ordering fix**: `update_bm`/`update_staffing` now validate BEFORE reverting PO counters (prevents negative qty_staffed on failed 400)
- **Frontend UX**: BM dialog shows "Total PO: X • Sudah Diterima: Y • Sisa: Z"; Staffing shows "Total PO: X • Sudah dikirim: Y • Sisa: Z"; edit dialogs recalculate sisa by subtracting own record's contribution
- **Rekap PO export** (Excel/CSV): added `Status` column with joined labels (Komplit SPK, Komplit Pengrajin, Komplit Terkirim, Ready, or Proses)
- Cleanup: purged 5 leftover TEST_ITER6_* PO records
- Tests: 16/16 backend pass + full frontend flows verified (iter6)

### Iteration 5 (Feb 2026) - PO Status Badges + Staffing Sisa
- **Staffing qty auto-limit**: Max = qty_po - qty_staffed (updates after each staffing)
- **PO items** now have `qty_staffed` field auto-updated by create/update/delete staffing
- **Rekap PO Status Badges** (4 total):
  - `Komplit SPK` (blue): all barang in PO have SPK entry with matching no_po
  - `Komplit Pengrajin` (green): all qty_diterima >= qty_po
  - `Komplit Terkirim` (purple): all qty_staffed >= qty_po
  - `Ready` (yellow): all packing >= qty_po (fully progressed)
- Staffing dialog shows "Total PO: X • Sudah dikirim: Y • Sisa: Z" per item
- Migration script backfilled qty_staffed for existing POs
- Tests: 11/11 backend pass

### Iteration 4 (Feb 2026)
- BM qty limit auto from PO
- Staffing item selection + qty limit + PDF/Excel/Print
- Excel exports with embedded images (80x80 thumbnails)
- Landscape A4 print CSS with small images (max 50px, contain), compact tables 9px
- Rekap Staffing redesigned: [Foto, No PO, Barang, Qty PO, Qty Staffing, Kurang Kirim]
- BM search matches nama_barang & nama_pengrajin
- Legacy progres cleanup on startup

### Iteration 3 (Feb 2026)
- Progres Barang refactor: PO-grouped, syncs from BM, packing capped at qty_masuk
- Progres PDF export with tanggal filter
- Rekap PO filter dropdown
- DELETE 404 responses

### Iteration 2 (Feb 2026)
- User Management CRUD
- Delete/Edit/Search/Preview all resources
- SPK auto-fill from PO with photos + signatures
- Rekap: 5 tabs

### Iteration 1 (Feb 2026 - MVP)
- Auth, RBAC, 7 core modules, image upload, exports, mobile responsive

## Deferred / Backlog

### P1
- **Split server.py** (~1750 lines) into router modules - flagged 4 iterations in a row
- MongoDB $lookup aggregation pipelines for rekap (replace Python O(n²) joins)
- Compound unique index on progres (po_id, item_id)
- One-time migration script to purge legacy progres with empty po_id

### P2
- Multi-pengrajin per barang
- WhatsApp/Twilio notifications
- Barcode/QR scanning
- Audit log
- Charts (Recharts) in Rekap Data

## API Summary
- Auth: /api/auth/{login|me|logout}
- Upload: /api/upload, /api/files/{path}
- CRUD: /api/{barang|po|barang-masuk|staffing|spk|users}
- Progres: GET/POST /api/progres, GET /api/progres/by-po
- Rekap: /api/rekap/{all-po|per-pengrajin|per-barang|progres|staffing-detail|staffing-summary}
  - all-po now returns 4 status flags per row
- Exports PDF: /api/export/{po|spk|barang-masuk|staffing}/{id}/pdf, /api/export/{barang-masuk|staffing|progres}/pdf
- Exports Excel (with images): /api/export/{barang-masuk|staffing}/excel
