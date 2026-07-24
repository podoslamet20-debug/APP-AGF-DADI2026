# AGFDATA - Furniture Data Management System

## Original Problem Statement
Aplikasi rekap data barang furniture "AGFDATA" dengan menu Database Barang, PO, Barang Masuk, Staffing, SPK, Progres Barang, dan Rekap Data. Aplikasi harus mobile responsive dan mendukung 3 role: admin (full access), staff (edit barang masuk/staffing/progres, harga disembunyikan), dan tamu (view only, harga dan nama pengrajin disembunyikan).

## Architecture
- **Backend**: FastAPI + MongoDB (Motor async) + JWT auth via httpOnly cookies
- **Frontend**: React + shadcn/ui + Tailwind CSS + react-router-dom
- **Storage**: Emergent Object Storage for image uploads
- **Exports**: ReportLab (PDF with images), pandas + xlsxwriter (Excel), XLSX.js (CSV/Excel)

## User Personas
1. **Admin**: Full access, user management, all filters
2. **Staff**: Edit Barang Masuk/Staffing/Progres, prices hidden, all filters
3. **Tamu (Guest)**: View-only, prices + craftsman hidden, all filters usable

## Test Credentials
- Admin: admin@agfdata.com / admin123
- Staff: staff@agfdata.com / staff123
- Tamu: tamu@agfdata.com / tamu123

## Implementation History

### Iteration 1 (Feb 2026 - MVP)
- Auth, RBAC, 7 core modules (Barang/PO/BM/Staffing/SPK/Progres/Rekap), image upload, exports, mobile responsive

### Iteration 2 (Feb 2026 - Enhancements)
- User Management CRUD, Delete/Edit/Search/Preview across all resources
- SPK auto-fill from PO, PDF with images + signature area
- Rekap: 5 tabs (PO/Per Barang/Progres/Pengrajin/Staffing)
- "Remaining" → "Kurang Kirim"

### Iteration 3 (Feb 2026 - Progres Refactor + Filters)
- Progres Barang: PO-based grouping (`GET /api/progres/by-po`), syncs from barang masuk
- Packing qty capped at qty_masuk (auto-clamped when qty_masuk=0)
- Progres PDF export with optional tanggal filter (`GET /api/export/progres/pdf?tanggal=YYYY-MM-DD`)
- Print CSS: hides sidebar/header/buttons on `window.print()`
- Barang Masuk: checkbox to select which items to include from PO
- Rekap PO: Filter dropdown by No PO (`?no_po=X`)
- Rekap Per Barang: Also filters by no_po
- DELETE endpoints return proper 404 with detail message
- All filters accessible to admin/staff/guest

## Backlog

### P1
- Split server.py (~1415 lines) into router modules (backend/routers/)
- MongoDB aggregation pipelines for rekap queries (currently O(n²) Python joins)
- Charts/visualizations in Rekap Data

### P2
- One-time migration to normalize legacy progres records (empty po_id)
- WhatsApp/Twilio notifications for pengrajin
- Barcode/QR scanning for check-in
- Multi-file image gallery per barang
- Audit log

## API Endpoints Summary
### Auth
POST /api/auth/login, GET /api/auth/me, POST /api/auth/logout

### File Upload/Download
POST /api/upload, GET /api/files/{path}

### Resources (CRUD)
- /api/barang (search)
- /api/po (search)
- /api/barang-masuk
- /api/staffing (filter tanggal)
- /api/spk (search)
- /api/users (admin only)

### Progres
GET/POST /api/progres, GET /api/progres/by-po

### Rekap
- GET /api/rekap/all-po?no_po=X
- GET /api/rekap/per-pengrajin
- GET /api/rekap/per-barang?no_po=X
- GET /api/rekap/progres
- GET /api/rekap/staffing-detail?tanggal_from&tanggal_to

### Exports
- GET /api/export/po/{id}/pdf
- GET /api/export/spk/{id}/pdf
- GET /api/export/barang-masuk/{id}/pdf
- GET /api/export/staffing/{id}/pdf
- GET /api/export/progres/pdf?tanggal=YYYY-MM-DD
- GET /api/export/barang-masuk/excel
