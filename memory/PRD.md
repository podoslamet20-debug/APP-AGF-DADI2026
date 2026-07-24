# AGFDATA - Furniture Data Management System

## Original Problem Statement
Aplikasi rekap data barang furniture "AGFDATA" dengan menu Database Barang, PO, Barang Masuk, Staffing, SPK, Progres Barang, dan Rekap Data. Aplikasi harus mobile responsive dan mendukung 3 role: admin (full access), staff (edit barang masuk/staffing/progres, harga disembunyikan), dan tamu (view only, harga dan nama pengrajin disembunyikan).

## Architecture
- **Backend**: FastAPI + MongoDB (Motor async) + JWT auth via httpOnly cookies
- **Frontend**: React + shadcn/ui + Tailwind CSS + react-router-dom
- **Storage**: Emergent Object Storage for image uploads
- **Exports**: ReportLab (PDF), pandas + xlsxwriter (Excel), XLSX.js (client-side CSV/Excel)

## User Personas
1. **Admin**: Full access to all modules including CRUD, pricing, and craftsman data
2. **Staff**: Can edit Barang Masuk, Staffing, and Progres Barang. Prices are hidden.
3. **Tamu (Guest)**: View-only access. Prices and craftsman names are hidden.

## What's Been Implemented (Feb 2026)
- [x] JWT authentication with role-based access control (admin/staff/guest)
- [x] Database Barang: CRUD + image upload + search/filter
- [x] PO (Purchase Order): Multi-item, auto-fill from Barang DB, edit, PDF export, search
- [x] Barang Masuk: Auto-fill from PO, qty tracking (updates PO qty_diterima), Excel export
- [x] Staffing: Auto-fill from PO, date-based tracking
- [x] SPK: Multi-item, auto-fill, edit, PDF export, includes signature area
- [x] Progres Barang: Grinda → Servis → Finishing → Packing with "KOMPLIT" badge
- [x] Rekap Data: Tabs for PO/Pengrajin/Staffing with date filter, CSV/Excel export
- [x] Role-based UI hiding (prices for staff/guest, craftsmen for guest)
- [x] Mobile responsive layout with sidebar drawer
- [x] Login page with demo credentials displayed

## Test Credentials
- Admin: admin@agfdata.com / admin123
- Staff: staff@agfdata.com / staff123
- Tamu: tamu@agfdata.com / tamu123

## Backlog / Prioritized

### P1 (Enhancements)
- DELETE endpoints for all resources
- PDF export for Barang Masuk & Staffing
- Print layout page (separate print CSS)
- Progres Barang: link to specific barang masuk item (currently generic)
- Charts/visualizations in Rekap Data (Recharts already installed)
- Notification/toast for near-complete PO deliveries

### P2 (Future)
- User management UI (create/edit/delete users)
- Multi-file image gallery per barang
- Advanced filtering (date range, status)
- Audit log for admin actions
- Real-time updates via websockets
- Bulk import from Excel

## Next Tasks
1. Add DELETE endpoints and confirmation dialogs
2. Extend PDF/print layouts to include images and better styling
3. Add data validation (unique No PO warning, negative qty, etc.)
4. Charts in Rekap Data dashboard

## API Endpoints Summary
- POST /api/auth/login, GET /api/auth/me, POST /api/auth/logout
- POST /api/upload, GET /api/files/{path}
- CRUD /api/barang (search)
- CRUD /api/po (search, edit)
- POST/GET /api/barang-masuk
- POST/GET /api/staffing (filter by date)
- CRUD /api/spk (search, edit)
- POST/GET /api/progres
- GET /api/rekap/all-po, /api/rekap/per-pengrajin
- GET /api/export/po/{id}/pdf
- GET /api/export/spk/{id}/pdf
- GET /api/export/barang-masuk/excel
