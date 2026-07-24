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
- **Split server.py** (1617 lines) into router modules - flagged 3 iterations in a row
- MongoDB $lookup aggregation pipelines for rekap (replace Python O(n²) joins)
- Compound unique index on progres (po_id, item_id)
- `update_po` preserves qty_staffed on edit (currently resets to 0)

### P2
- Pydantic StaffingItem/BarangMasukItem models (currently raw list[dict])
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
