# AGFDATA - Furniture Data Management System

## Original Problem Statement
Aplikasi rekap data barang furniture "AGFDATA" dengan menu Database Barang, PO, Barang Masuk, Staffing, SPK, Progres Barang, dan Rekap Data. Aplikasi harus mobile responsive dan mendukung 3 role: admin (full access), staff (edit barang masuk/staffing/progres, harga disembunyikan), dan tamu (view only, harga dan nama pengrajin disembunyikan).

## Architecture
- **Backend**: FastAPI + MongoDB (Motor async) + JWT auth via httpOnly cookies
- **Frontend**: React + shadcn/ui + Tailwind CSS + react-router-dom
- **Storage**: Emergent Object Storage for image uploads
- **Exports**: ReportLab (PDF with images), pandas + xlsxwriter (Excel), XLSX.js (CSV/Excel)

## User Personas
1. **Admin**: Full access to all modules including CRUD, pricing, craftsman data, and user management
2. **Staff**: Can edit Barang Masuk, Staffing, and Progres Barang. Prices are hidden.
3. **Tamu (Guest)**: View-only access. Prices and craftsman names are hidden.

## Test Credentials
- Admin: admin@agfdata.com / admin123
- Staff: staff@agfdata.com / staff123
- Tamu: tamu@agfdata.com / tamu123

## What's Been Implemented

### Iteration 1 (Feb 2026 - MVP)
- [x] JWT authentication with role-based access control
- [x] Database Barang: CRUD + image upload + search/filter
- [x] PO (Purchase Order): Multi-item, auto-fill from Barang DB, edit, PDF export, search
- [x] Barang Masuk: Auto-fill from PO, qty tracking (updates PO qty_diterima)
- [x] Staffing: Auto-fill from PO, date-based tracking
- [x] SPK: Multi-item, auto-fill, edit, PDF export with signature area
- [x] Progres Barang: Grinda → Servis → Finishing → Packing with "KOMPLIT" badge
- [x] Rekap Data: 3 tabs (PO/Pengrajin/Staffing) with CSV/Excel export
- [x] Role-based UI hiding (prices for staff/guest, craftsmen for guest)
- [x] Mobile responsive layout

### Iteration 2 (Feb 2026 - Enhancements)
- [x] User Management: Full CRUD for admin/staff/tamu users (admin-only)
- [x] Delete endpoints for ALL resources (barang, PO, BM, staffing, SPK) with confirmation dialogs
- [x] Edit functionality for ALL menus (barang, BM, staffing added)
- [x] Search for ALL menus (BM, staffing added)
- [x] Preview modals for ALL menus (barang, BM, staffing, SPK detail dialogs)
- [x] SPK auto-fill from PO: "Import dari PO" dropdown loads items with pengrajin, harga, foto
- [x] SPK PDF: Includes photos + signature area for owner & pengrajin + payment notes
- [x] PDF exports for Barang Masuk & Staffing (new)
- [x] All PDFs now include product photos with branded header
- [x] Rekap Data expanded to 5 tabs: Rekap PO, Per Barang, Progres, Per Pengrajin, Staffing
- [x] "Remaining" renamed to "Kurang Kirim" in Rekap PO
- [x] Rekap Per Barang: Barang Masuk - Progres Packing
- [x] Rekap Progres: Full tracking with KOMPLIT/PROSES badges
- [x] Client-side route guard: non-admin users redirected from /users

## Backlog

### P1 (Enhancements)
- Print CSS separate for print pages (currently PDF only)
- Charts/visualizations in Rekap Data (Recharts installed)
- Notifications for near-complete PO deliveries
- Bulk import from Excel

### P2 (Future)
- Multi-file image gallery per barang
- Advanced filtering (date range, status)
- Audit log for admin actions
- Real-time updates via websockets
- WhatsApp notification integration to craftsmen (via Twilio)

## API Endpoints Summary
### Auth
- POST /api/auth/login, GET /api/auth/me, POST /api/auth/logout

### File Upload
- POST /api/upload, GET /api/files/{path}

### Barang
- GET/POST/PUT/DELETE /api/barang (with search)

### PO
- GET/POST/PUT/DELETE /api/po (with search)

### Barang Masuk
- GET/POST/PUT/DELETE /api/barang-masuk

### Staffing
- GET/POST/PUT/DELETE /api/staffing (filter by tanggal)

### SPK
- GET/POST/PUT/DELETE /api/spk (with search)

### Progres
- GET/POST /api/progres

### Rekap
- GET /api/rekap/all-po
- GET /api/rekap/per-pengrajin
- GET /api/rekap/per-barang
- GET /api/rekap/progres
- GET /api/rekap/staffing-detail

### Users (admin only)
- GET/POST/PUT/DELETE /api/users

### Exports
- GET /api/export/po/{id}/pdf
- GET /api/export/spk/{id}/pdf
- GET /api/export/barang-masuk/{id}/pdf
- GET /api/export/staffing/{id}/pdf
- GET /api/export/barang-masuk/excel
