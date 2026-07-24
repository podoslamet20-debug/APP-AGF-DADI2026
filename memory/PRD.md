# AGFDATA - Furniture Data Management System

## Original Problem Statement
Aplikasi rekap data barang furniture "AGFDATA" - Database Barang, PO, Barang Masuk, Staffing, SPK, Progres Barang, Rekap Data dengan 3 role (admin/staff/tamu), mobile responsive.

## Architecture
- Backend: FastAPI + MongoDB (Motor) + JWT httpOnly cookies
- Frontend: React + shadcn/ui + Tailwind
- Storage: Emergent Object Storage
- Exports: ReportLab (PDF+images), xlsxwriter (Excel+embedded images), XLSX.js (CSV)

## Test Credentials
- Admin: admin@agfdata.com / admin123
- Staff: staff@agfdata.com / staff123
- Tamu: tamu@agfdata.com / tamu123

## Implementation Log

### Iteration 4 (Feb 2026 - Filter, Export & Print refinement)
- Barang Masuk qty auto-limited to (PO qty - already received)
- Staffing: item selection with checkbox + qty limit from PO qty + PDF/Excel/Print buttons
- Progres Print CSS: landscape A4, images small (max 50px), compact table 9px
- Rekap Data: Print button in header, landscape print
- Rekap Staffing redesigned: [Foto, No PO, Barang, Qty PO, Qty Staffing, Kurang Kirim] - removed pengrajin, added Qty PO & Kurang Kirim
- Barang Masuk: search now matches nama_barang & nama_pengrajin (not just no_po/penerima) + PDF/Excel/Print buttons with search-based filter
- Excel exports: photo column with embedded thumbnails (80x80) via xlsxwriter insert_image
- Startup migration: cleans legacy progres records with empty po_id

### Iteration 3 (Feb 2026)
- Progres Barang refactor: PO-based grouping, syncs from barang masuk, packing capped at qty_masuk
- Progres PDF export with tanggal filter
- Barang Masuk item selection (checkbox)
- Rekap PO filter dropdown by No PO
- DELETE 404 responses
- Print CSS foundation

### Iteration 2 (Feb 2026)
- User Management CRUD, Delete/Edit/Search/Preview across all resources
- SPK auto-fill from PO, improved PDF with images + signatures
- Rekap: 5 tabs (PO/Per Barang/Progres/Pengrajin/Staffing)

### Iteration 1 (Feb 2026 - MVP)
- Auth, RBAC, 7 core modules, image upload, exports, mobile responsive

## Deferred / Backlog

### P1
- Split server.py into router modules (currently ~1500 lines but working stable)
- MongoDB aggregation pipelines for rekap queries (replace Python O(n²) joins)
- Charts/visualizations (Recharts) in Rekap Data

### P2
- Multi-pengrajin per barang (currently single string field)
- WhatsApp/Twilio notifications
- Barcode/QR scanning
- Audit log

## API Summary
- Auth: /api/auth/login|me|logout
- Upload: /api/upload, /api/files/{path}
- CRUD: /api/{barang|po|barang-masuk|staffing|spk|users}
- Progres: GET/POST /api/progres, GET /api/progres/by-po
- Rekap: /api/rekap/{all-po|per-pengrajin|per-barang|progres|staffing-detail|staffing-summary}
- Exports (PDF): /api/export/{po|spk|barang-masuk|staffing}/{id}/pdf, /api/export/{barang-masuk|staffing|progres}/pdf, /api/export/progres/pdf?tanggal=
- Exports (Excel with images): /api/export/{barang-masuk|staffing}/excel
